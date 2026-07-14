import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import psutil


OLLAMA_BASE_URL = "http://localhost:11434"


def _gb(value: int | float | None) -> float:
    return round(float(value or 0) / (1024 ** 3), 2)


def _read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_int_file(path: Path) -> Optional[int]:
    raw = _read_text_file(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_uevent(path: Path) -> Dict[str, str]:
    raw = _read_text_file(path)
    if not raw:
        return {}
    parsed = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[key] = value
    return parsed


def get_cpu_temperature() -> Optional[float]:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for key in ["coretemp", "k10temp", "zenpower", "cpu_thermal", "cpu-thermal"]:
            if key in temps and temps[key]:
                return temps[key][0].current
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    return None


def _read_hwmon_temperature(device_path: Path) -> Optional[float]:
    hwmon_root = device_path / "hwmon"
    if not hwmon_root.exists():
        return None

    preferred_labels = {"edge", "junction", "tctl", "gpu"}
    fallback = None
    for hwmon_dir in sorted(hwmon_root.glob("hwmon*")):
        for temp_input in sorted(hwmon_dir.glob("temp*_input")):
            raw_value = _read_text_file(temp_input)
            if not raw_value:
                continue
            try:
                current = round(int(raw_value) / 1000, 1)
            except ValueError:
                continue

            label_path = temp_input.with_name(temp_input.name.replace("_input", "_label"))
            label = (_read_text_file(label_path) or "").strip().lower()
            if label in preferred_labels:
                return current
            if fallback is None:
                fallback = current
    return fallback


def _read_gpu_memory_info(device_path: Path) -> Dict[str, float]:
    raw = {
        "vram_total": _read_int_file(device_path / "mem_info_vram_total"),
        "vram_used": _read_int_file(device_path / "mem_info_vram_used"),
        "gtt_total": _read_int_file(device_path / "mem_info_gtt_total"),
        "gtt_used": _read_int_file(device_path / "mem_info_gtt_used"),
    }
    return {
        "vram_total_gb": _gb(raw["vram_total"]),
        "vram_used_gb": _gb(raw["vram_used"]),
        "gtt_total_gb": _gb(raw["gtt_total"]),
        "gtt_used_gb": _gb(raw["gtt_used"]),
    }


def get_amd_gpu_devices(drm_root: Path = Path("/sys/class/drm")) -> list[Dict[str, Any]]:
    devices = []
    if not drm_root.exists():
        return devices

    for card_path in sorted(drm_root.glob("card[0-9]*")):
        device_path = card_path / "device"
        vendor = _read_text_file(device_path / "vendor")
        if vendor != "0x1002":
            continue

        uevent = _parse_uevent(device_path / "uevent")
        pci_id = uevent.get("PCI_ID")
        device_id = _read_text_file(device_path / "device")
        if not pci_id and device_id:
            pci_id = f"1002:{device_id.removeprefix('0x').upper()}"

        memory = _read_gpu_memory_info(device_path)
        shared_memory_likely = bool(memory["gtt_total_gb"]) and (
            not memory["vram_total_gb"] or memory["gtt_total_gb"] >= memory["vram_total_gb"]
        )
        devices.append({
            "card": card_path.name,
            "driver": uevent.get("DRIVER"),
            "pci_id": pci_id,
            "device_id": device_id,
            "temperature_c": _read_hwmon_temperature(device_path),
            "memory": memory,
            "shared_memory_likely": shared_memory_likely,
        })
    return devices


def summarize_ollama_runtime(
    models: list[Dict[str, Any]],
    gpu_devices: Optional[list[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if not models:
        return {
            "status": "idle",
            "processor": "IDLE",
            "loaded_models": 0,
            "size_gb": 0,
            "vram_gb": 0,
            "ram_gb": 0,
            "memory_target": "idle",
            "memory_label": "sem modelo carregado",
            "models": [],
        }

    total_size = sum(int(model.get("size") or 0) for model in models)
    total_vram = sum(int(model.get("size_vram") or 0) for model in models)
    total_ram = max(0, total_size - total_vram)
    shared_gpu_memory = any((device or {}).get("shared_memory_likely") for device in gpu_devices or [])

    if total_vram <= 0:
        processor = "CPU"
        memory_target = "system_ram"
        memory_label = "RAM do sistema"
    elif total_size and total_vram >= total_size * 0.95:
        processor = "GPU"
        memory_target = "shared_gpu_ram" if shared_gpu_memory else "gpu_memory"
        memory_label = "memoria de video compartilhada (RAM)" if shared_gpu_memory else "memoria de video/VRAM"
    else:
        processor = "CPU/GPU"
        memory_target = "mixed_shared_gpu_ram" if shared_gpu_memory else "mixed"
        memory_label = "RAM + memoria de video compartilhada" if shared_gpu_memory else "RAM + memoria de video/VRAM"

    return {
        "status": "loaded",
        "processor": processor,
        "loaded_models": len(models),
        "size_gb": _gb(total_size),
        "vram_gb": _gb(total_vram),
        "ram_gb": _gb(total_ram),
        "memory_target": memory_target,
        "memory_label": memory_label,
        "models": [
            {
                "name": model.get("name") or model.get("model"),
                "size_gb": _gb(model.get("size")),
                "vram_gb": _gb(model.get("size_vram")),
                "context_length": model.get("context_length"),
            }
            for model in models
        ],
    }


async def get_ollama_runtime(
    gpu_devices: Optional[list[Dict[str, Any]]] = None,
    base_url: str = OLLAMA_BASE_URL,
) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=0.6) as client:
            response = await client.get(f"{base_url}/api/ps")
        if response.status_code != 200:
            return {"status": "unavailable", "processor": "N/A", "loaded_models": 0}
        models = response.json().get("models", [])
        return summarize_ollama_runtime(models, gpu_devices=gpu_devices)
    except Exception:
        return {"status": "offline", "processor": "N/A", "loaded_models": 0}


async def collect_system_snapshot(label: Optional[str] = None) -> Dict[str, Any]:
    ram = psutil.virtual_memory()
    gpu_devices = get_amd_gpu_devices()
    ollama_runtime = await get_ollama_runtime(gpu_devices=gpu_devices)
    temp = get_cpu_temperature()
    snapshot = {
        "timestamp": time.time(),
        "label": label,
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_total_gb": round(ram.total / (1024 ** 3), 2),
        "ram_used_gb": round((ram.total - ram.available) / (1024 ** 3), 2),
        "ram_percent": ram.percent,
        "cpu_temp": round(temp, 1) if temp is not None else None,
        "gpu": {
            "amd_detected": bool(gpu_devices),
            "amd_devices": gpu_devices,
        },
        "ollama": ollama_runtime,
    }
    return snapshot


def format_hardware_snapshot_log(snapshot: Dict[str, Any]) -> str:
    label = snapshot.get("label") or "snapshot"
    ollama = snapshot.get("ollama") or {}
    gpu_devices = ((snapshot.get("gpu") or {}).get("amd_devices") or [])
    gpu_memory = ""
    if gpu_devices:
        memory = (gpu_devices[0] or {}).get("memory") or {}
        gpu_memory = (
            f" | GPU mem: VRAM {memory.get('vram_used_gb', 0):.2f}/"
            f"{memory.get('vram_total_gb', 0):.2f} GB, GTT {memory.get('gtt_used_gb', 0):.2f}/"
            f"{memory.get('gtt_total_gb', 0):.2f} GB"
        )
    temp = snapshot.get("cpu_temp")
    temp_text = "N/A" if temp is None else f"{temp:.1f}C"
    return (
        f"Hardware ({label}): CPU {snapshot.get('cpu_percent', 0):.1f}% | "
        f"RAM {snapshot.get('ram_used_gb', 0):.2f}/{snapshot.get('ram_total_gb', 0):.2f} GB | "
        f"Temp {temp_text} | "
        f"LLM {ollama.get('processor', 'N/A')} "
        f"({ollama.get('vram_gb', 0):.2f} GB; {ollama.get('memory_label', 'N/A')})"
        f"{gpu_memory}"
    )
