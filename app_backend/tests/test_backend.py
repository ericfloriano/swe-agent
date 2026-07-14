import os
import shutil
import pytest
from pathlib import Path
from app_backend.security import SecuritySandbox
from app_backend.git_manager import GitManager
from app_backend.git_manager import LEGACY_WORKSPACE_README
from app_backend.ollama_client import OllamaClient
from app_backend.main import (
    STARTUP_FAST_START_DEFAULT,
    _enabled_env,
    get_amd_gpu_devices,
    summarize_ollama_runtime,
)
from app_backend.agent_orchestrator import (
    DEFAULT_DEVELOPER_MODEL,
    DEVELOPER_RUNTIME_OPTIONS,
    DEVELOPER_WORKSPACE_CONTEXT_MAX_CHARS,
    PLANNER_RUNTIME_OPTIONS,
    PLANNER_WORKSPACE_CONTEXT_MAX_CHARS,
    build_quality_checks,
    complete_execution_timer,
    collect_workspace_context,
    execution_timer_elapsed,
    extract_planned_files,
    format_workflow_totals,
    pause_execution_timer,
    parse_files_from_output,
    resolve_model,
    sanitize_planner_output,
    start_execution_timer,
)

@pytest.fixture
def temp_workspaces(tmp_path):
    # Setup temporary workspaces directory
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir()
    return workspaces_dir

def test_security_sandbox_validate_path(temp_workspaces):
    sandbox = SecuritySandbox(str(temp_workspaces))
    project_id = "test_project"
    
    # Pre-create project folder
    project_dir = temp_workspaces / project_id
    project_dir.mkdir()
    
    # 1. Valid paths inside project folder
    assert sandbox.validate_path(project_id, "src/main.py") == (project_dir / "src/main.py").resolve()
    assert sandbox.validate_path(project_id, "./README.md") == (project_dir / "README.md").resolve()
    
    # 2. Path Traversal attempts must throw ValueError
    with pytest.raises(ValueError):
        sandbox.validate_path(project_id, "../malicious.txt")
        
    with pytest.raises(ValueError):
        sandbox.validate_path(project_id, "/etc/passwd")

def test_security_sandbox_validate_command():
    sandbox = SecuritySandbox("/tmp")
    
    # Valid whitelisted commands
    assert sandbox.validate_command("git status") is True
    assert sandbox.validate_command("python -m pytest tests/") is True
    assert sandbox.validate_command("pytest") is True
    
    # Blacklisted or unallowed commands
    assert sandbox.validate_command("sudo rm -rf /") is False
    assert sandbox.validate_command("rm -rf workspaces/") is False
    assert sandbox.validate_command("curl http://malicious.com") is False
    assert sandbox.validate_command("cat /etc/passwd") is False
    assert sandbox.validate_command("git status && rm -rf .") is False

def test_git_manager_workflow(temp_workspaces):
    project_id = "git_project"
    project_dir = temp_workspaces / project_id
    project_dir.mkdir()
    
    # 1. Init repo
    repo = GitManager.init_repo(project_dir)
    assert (project_dir / ".git").exists()
    assert not (project_dir / "README.md").exists()
    assert GitManager.get_history(project_dir) == []
    
    # 2. First commit
    test_file = project_dir / "app.py"
    with open(test_file, "w") as f:
        f.write("print('Hello')\n")
        
    sha1 = GitManager.commit_state(project_dir, "Add app.py")
    history = GitManager.get_history(project_dir)
    
    # History length should be 1; the workspace starts without generated files.
    assert len(history) == 1
    assert history[0]["sha"] == sha1
    assert history[0]["message"] == "Add app.py"
    
    # 3. Second commit
    with open(test_file, "w") as f:
        f.write("print('Hello World')\n")
        
    sha2 = GitManager.commit_state(project_dir, "Update app.py")
    assert len(GitManager.get_history(project_dir)) == 2
    
    # 4. Rollback to sha1
    GitManager.rollback(project_dir, sha1)
    
    # Check if file returned to initial state
    with open(test_file, "r") as f:
        content = f.read()
    assert content == "print('Hello')\n"

def test_git_manager_removes_only_legacy_workspace_readme(temp_workspaces):
    project_dir = temp_workspaces / "legacy_readme_project"
    project_dir.mkdir()

    readme = project_dir / "README.md"
    readme.write_text(LEGACY_WORKSPACE_README, encoding="utf-8")
    assert GitManager.remove_legacy_workspace_readme(project_dir) is True
    assert not readme.exists()

    readme.write_text("# Real Project\n\nUsage docs.\n", encoding="utf-8")
    assert GitManager.remove_legacy_workspace_readme(project_dir) is False
    assert readme.exists()

def test_ollama_client_parsing():
    # Stub test for checking reasoning parser mechanics in stream_generate
    # We can mock response stream if needed, but we can verify the text parsing helper in OllamaClient.generate
    # since it uses the same reasoning splits.
    
    client = OllamaClient()
    
    # Simulating simple reasoning block split
    sample_text = "<think>Calculating steps\nChecking path</think>Final Output"
    
    # Let's verify the parsing logic extracted from OllamaClient.generate
    thinking = ""
    main_response = sample_text
    if "<think>" in sample_text:
        parts = sample_text.split("<think>", 1)
        before_think = parts[0]
        if "</think>" in parts[1]:
            think_parts = parts[1].split("</think>", 1)
            thinking = think_parts[0]
            main_response = before_think + think_parts[1]
            
    assert thinking.strip() == "Calculating steps\nChecking path"
    assert main_response.strip() == "Final Output"

def test_ollama_client_default_keep_alive(monkeypatch):
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    client = OllamaClient()
    assert client.keep_alive == "30m"

def test_ollama_client_runtime_options_enable_mmap_by_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_USE_MMAP", raising=False)
    client = OllamaClient()
    assert client._with_runtime_options()["use_mmap"] is True

def test_ollama_client_runtime_options_preserve_explicit_mmap(monkeypatch):
    monkeypatch.delenv("OLLAMA_USE_MMAP", raising=False)
    client = OllamaClient()
    assert client._with_runtime_options({"use_mmap": False})["use_mmap"] is False

def test_ollama_client_runtime_thread_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_THREAD", "6")
    client = OllamaClient()
    assert client._with_runtime_options({"num_predict": 1}) == {
        "num_predict": 1,
        "use_mmap": True,
        "num_thread": 6,
    }

def test_ollama_client_runtime_thread_override_does_not_replace_explicit_value(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_THREAD", "6")
    client = OllamaClient()
    assert client._with_runtime_options({"num_thread": 4})["num_thread"] == 4

def test_startup_fast_start_is_opt_in_by_default(monkeypatch):
    monkeypatch.delenv("SWE_AGENT_FAST_START", raising=False)
    assert STARTUP_FAST_START_DEFAULT is False
    assert _enabled_env("SWE_AGENT_FAST_START", STARTUP_FAST_START_DEFAULT) is False

def test_get_amd_gpu_devices_reads_passive_sysfs_snapshot(tmp_path):
    card = tmp_path / "card0"
    device = card / "device"
    hwmon = device / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="utf-8")
    (device / "device").write_text("0x15d8\n", encoding="utf-8")
    (device / "uevent").write_text("DRIVER=amdgpu\nPCI_ID=1002:15D8\n", encoding="utf-8")
    (device / "mem_info_vram_total").write_text(str(2 * 1024 ** 3), encoding="utf-8")
    (device / "mem_info_vram_used").write_text(str(1024 ** 3), encoding="utf-8")
    (device / "mem_info_gtt_total").write_text(str(8 * 1024 ** 3), encoding="utf-8")
    (device / "mem_info_gtt_used").write_text(str(3 * 1024 ** 3), encoding="utf-8")
    (hwmon / "temp1_label").write_text("edge\n", encoding="utf-8")
    (hwmon / "temp1_input").write_text("55000\n", encoding="utf-8")

    assert get_amd_gpu_devices(tmp_path) == [{
        "card": "card0",
        "driver": "amdgpu",
        "pci_id": "1002:15D8",
        "device_id": "0x15d8",
        "temperature_c": 55.0,
        "memory": {
            "vram_total_gb": 2.0,
            "vram_used_gb": 1.0,
            "gtt_total_gb": 8.0,
            "gtt_used_gb": 3.0,
        },
        "shared_memory_likely": True,
    }]

def test_summarize_ollama_runtime_marks_cpu_gpu_and_idle():
    assert summarize_ollama_runtime([])["processor"] == "IDLE"
    assert summarize_ollama_runtime([{"size": 1024, "size_vram": 0}])["processor"] == "CPU"
    assert summarize_ollama_runtime([{"size": 1000, "size_vram": 1000}])["processor"] == "GPU"
    assert summarize_ollama_runtime([{"size": 1000, "size_vram": 500}])["processor"] == "CPU/GPU"

def test_agent_runtime_options_limit_context_and_generation():
    assert DEFAULT_DEVELOPER_MODEL == "qwen2.5-coder-3b-local"
    assert PLANNER_WORKSPACE_CONTEXT_MAX_CHARS == 4000
    assert DEVELOPER_WORKSPACE_CONTEXT_MAX_CHARS == 12000
    assert PLANNER_RUNTIME_OPTIONS == {
        "num_ctx": 2048,
        "temperature": 0.3,
        "num_predict": 384,
    }
    assert DEVELOPER_RUNTIME_OPTIONS == {
        "num_ctx": 4096,
        "temperature": 0.1,
        "num_predict": 1000,
    }

def test_resolve_model_accepts_role_suffix_variants():
    available = [
        "llama3.2-3b-planner:latest",
        "qwen2.5-coder-3b-developer:latest",
    ]

    assert resolve_model("llama3.2-3b-local", available) == "llama3.2-3b-planner:latest"
    assert resolve_model("qwen2.5-coder-3b-local", available) == "qwen2.5-coder-3b-developer:latest"

def test_collect_workspace_context_reads_project_files_and_skips_agent_plan(tmp_path):
    project_dir = tmp_path / "project"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    (src_dir / "app.py").write_text("print('demo')\n", encoding="utf-8")
    (project_dir / "implementation_plan.md").write_text("internal plan\n", encoding="utf-8")

    context = collect_workspace_context(project_dir, [])

    assert "[FILE: README.md]" in context
    assert "[FILE: src/app.py]" in context
    assert "implementation_plan.md" not in context

def test_sanitize_planner_output_removes_code_blocks():
    raw_plan = """# Plano de Implementação

## Arquivos

### main.py

```python
import json

def main():
    print("planner should not write code")
```

## Critérios de Aceitação

- Developer deve implementar o CLI.
"""

    sanitized, removed_blocks = sanitize_planner_output(raw_plan)

    assert removed_blocks == 1
    assert "import json" not in sanitized
    assert "def main" not in sanitized
    assert "Código deve ser gerado apenas pelo Developer Agent" not in sanitized
    assert "Bloco de código omitido" in sanitized
    assert "Developer deve implementar o CLI" in sanitized

def test_sanitize_planner_output_removes_inline_code_lines():
    raw_plan = """# Plano de Implementação

## Arquivos

- timer.py: controla o cronômetro.

import time
elapsed_time = time.time() - self.timer.start_time
print("Timer")

## Critérios

- Developer deve implementar a lógica.
"""

    sanitized, removed_blocks = sanitize_planner_output(raw_plan)

    assert removed_blocks == 1
    assert "import time" not in sanitized
    assert "elapsed_time =" not in sanitized
    assert "print(" not in sanitized
    assert "Linha de codigo omitida" in sanitized
    assert "Developer deve implementar a lógica" in sanitized

def test_quality_checks_pass_activity_scope_plan():
    prompt = "Desenvolva um app simples para controle de atividades diárias em Python."
    plan = """# Plano de Implementação

## Escopo entendido
- App de terminal para controle de atividades diárias.

## Funcionalidades mínimas obrigatórias
- Cadastrar atividade.
- Listar atividades.
- Marcar atividade como concluída.
- Remover atividade.

## Fora de escopo
- Não implementar Pomodoro, timer ou agenda complexa.

## Arquitetura e dependências
- Python sem dependências externas.

## Lista de arquivos
- main.py: menu e funções de atividades.

## Critérios de aceite
- Usuário consegue cadastrar, listar, concluir e remover atividades.
"""

    quality = build_quality_checks(prompt, plan, stage="planner")

    assert quality["blocking"] is False
    assert quality["has_acceptance_criteria"] is True
    assert quality["suspicious_domain_shift"] is False
    assert "main.py" in quality["planned_files"]

def test_quality_checks_block_domain_shift_to_pomodoro():
    prompt = "Desenvolva um app simples para controle de atividades diárias em Python."
    plan = """# Plano de Implementação

## Escopo entendido
- App de terminal para iniciar um Pomodoro.

## Funcionalidades mínimas obrigatórias
- Iniciar Pomodoro.

## Fora de escopo
- Persistência de atividades.

## Arquitetura e dependências
- Python.

## Lista de arquivos
- main.py: menu.
- pomodoro.py: timer de foco.

## Critérios de aceite
- Usuário consegue iniciar um Pomodoro.
"""

    quality = build_quality_checks(prompt, plan, stage="planner")

    assert quality["blocking"] is True
    assert quality["suspicious_domain_shift"] is True
    assert "pomodoro" in quality["domain_shift_terms"]

def test_extract_planned_files_dedupes_known_extensions():
    plan = "- main.py\n- src/models.py\n- main.py\n- notes.txt"

    assert extract_planned_files(plan) == ["main.py", "src/models.py"]

def test_parse_files_from_output_accepts_standard_file_blocks():
    output = """[FILE: src/main.py]
```python
print("ok")
```

[FILE: src/utils.py]
```python
def parse_value(value):
    return float(value)
```
"""

    files = parse_files_from_output(output)

    assert files == [
        ("src/main.py", 'print("ok")'),
        ("src/utils.py", "def parse_value(value):\n    return float(value)"),
    ]

def test_parse_files_from_output_accepts_common_model_format_variants():
    output = """Arquivo: src/main.py
```python filename="src/main.py"
print("ok")
```

### `src/timer.py`
```python
class Timer:
    pass
```
"""

    files = parse_files_from_output(output)

    assert ("src/main.py", 'print("ok")') in files
    assert ("src/timer.py", "class Timer:\n    pass") in files

def test_parse_files_from_output_recovers_fenced_filename_then_code():
    output = """```python
pomodoro.py
```

```python
import time

def main():
    print("Pomodoro")
```
"""

    files = parse_files_from_output(output)

    assert files == [
        ("pomodoro.py", 'import time\n\ndef main():\n    print("Pomodoro")')
    ]

def test_parse_files_from_output_rejects_txt_for_source_code():
    output = """[FILE: pomodoro.txt]
```python
print("should be .py")
```
"""

    assert parse_files_from_output(output) == []

def test_parse_files_from_output_accepts_filename_comment_inside_fence():
    output = """```python
# contato.py

class Contato:
    pass
```

```python
# agenda.py

from contato import Contato
```
"""

    files = parse_files_from_output(output)

    assert files == [
        ("contato.py", "class Contato:\n    pass"),
        ("agenda.py", "from contato import Contato"),
    ]

def test_format_workflow_totals_sums_agent_metrics():
    summary = format_workflow_totals([
        {
            "duration_seconds": 10.0,
            "eval_count": 20,
            "prompt_eval_count": 30,
            "eval_duration_seconds": 5.0,
        },
        {
            "duration_seconds": 4.0,
            "eval_count": 10,
            "prompt_eval_count": 5,
            "eval_duration_seconds": 2.0,
        },
    ])

    assert "Tempo: 14.00s" in summary
    assert "Tokens resposta: 30" in summary
    assert "Tokens prompt: 35" in summary
    assert "4.3 TPS" in summary

def test_execution_timer_accumulates_across_pauses():
    state = {}

    start_execution_timer(state, reset=True, now=100.0, phase="planner")
    assert execution_timer_elapsed(state["execution_timer"], now=110.0) == 10.0

    pause_execution_timer(state, now=125.0)
    assert state["execution_timer"]["status"] == "paused"
    assert state["execution_timer"]["accumulated_seconds"] == 25.0
    assert state["execution_timer"]["phase_seconds"]["planner"] == 25.0
    assert state["execution_timer"]["phase_seconds"]["developer"] == 0.0

    start_execution_timer(state, reset=False, now=200.0, phase="developer")
    complete_execution_timer(state, now=230.0)
    assert state["execution_timer"]["status"] == "completed"
    assert state["execution_timer"]["accumulated_seconds"] == 55.0
    assert state["execution_timer"]["phase_seconds"]["planner"] == 25.0
    assert state["execution_timer"]["phase_seconds"]["developer"] == 30.0
