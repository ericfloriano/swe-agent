import os
import httpx
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_KEEP_ALIVE = "30m"

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("Ignoring invalid %s=%s", name, raw)
    return default

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", keep_alive: Optional[str] = None):
        self.base_url = base_url
        self.keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE)
        self.use_mmap = _env_bool("OLLAMA_USE_MMAP", True)

    def _with_runtime_options(self, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_options = dict(options or {})
        req_options.setdefault("use_mmap", self.use_mmap)
        thread_override = os.getenv("OLLAMA_NUM_THREAD")
        if thread_override:
            try:
                num_thread = int(thread_override)
                if num_thread > 0:
                    req_options.setdefault("num_thread", num_thread)
            except ValueError:
                logger.warning("Ignoring invalid OLLAMA_NUM_THREAD=%s", thread_override)
        else:
            req_options.setdefault("num_thread", 4)
        return req_options

    async def fast_start_model(self, model: str, keep_alive: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> bool:
        """
        Touches a model with an empty prompt so Ollama maps/loads it on demand
        without generating tokens. keep_alive controls how long it remains ready.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": keep_alive or self.keep_alive,
            "options": self._with_runtime_options(options),
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    load_ns = data.get("load_duration", 0)
                    load_s = load_ns / 1e9 if load_ns else 0
                    logger.info(f"Model {model} fast-started in {load_s:.1f}s")
                    return True
                else:
                    logger.warning(f"Failed to fast-start model {model}: HTTP {r.status_code}")
                    return False
        except Exception as e:
            logger.warning(f"Failed to fast-start model {model}: {e}")
            return False

    async def preload_model(self, model: str, keep_alive: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> bool:
        """Backward-compatible alias for the Fast Start model touch."""
        return await self.fast_start_model(model, keep_alive=keep_alive, options=options)

    async def stream_generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        keep_alive: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams generation from Ollama, yielding dictionaries categorizing tokens as 
        'thinking' (inside <think>...</think>) or 'response' (outside <think>...</think>).
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": keep_alive or self.keep_alive,
        }
        if system:
            payload["system"] = system
        
        payload["options"] = self._with_runtime_options(options)

        in_thinking = False
        buffer = ""

        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"Ollama returned error status {response.status_code}: {error_text}")
                        yield {"type": "error", "content": f"Ollama error: {response.status_code}"}
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            done = data.get("done", False)

                            if token:
                                buffer += token
                                
                                # Detect start of reasoning block
                                if "<think>" in buffer:
                                    in_thinking = True
                                    parts = buffer.split("<think>", 1)
                                    if parts[0]:
                                        yield {"type": "response", "content": parts[0]}
                                    buffer = ""
                                    continue
                                    
                                # Detect end of reasoning block
                                if "</think>" in buffer:
                                    in_thinking = False
                                    parts = buffer.split("</think>", 1)
                                    if parts[0]:
                                        yield {"type": "thinking", "content": parts[0]}
                                    buffer = parts[1]
                                    if buffer:
                                        yield {"type": "response", "content": buffer}
                                        buffer = ""
                                    continue

                                # Stream out contents dynamically
                                if not in_thinking:
                                    # Ensure we are not mid-tag construction
                                    if not any(tag.startswith(buffer) for tag in ["<think>", "</think>"]):
                                        yield {"type": "response", "content": buffer}
                                        buffer = ""
                                else:
                                    if not any(tag.startswith(buffer) for tag in ["</think>"]):
                                        yield {"type": "thinking", "content": buffer}
                                        buffer = ""

                            if done:
                                if buffer:
                                    yield {"type": "thinking" if in_thinking else "response", "content": buffer}
                                
                                # Send generation metrics to calculate tokens/sec in frontend
                                prompt_eval_count = data.get("prompt_eval_count")
                                eval_count = data.get("eval_count")
                                eval_duration = data.get("eval_duration")
                                total_duration = data.get("total_duration")
                                prompt_eval_duration = data.get("prompt_eval_duration")
                                load_duration = data.get("load_duration")
                                if eval_count is not None and eval_duration:
                                    tokens_sec = eval_count / (eval_duration / 1e9)
                                    yield {
                                        "type": "metrics",
                                        "prompt_eval_count": prompt_eval_count,
                                        "eval_count": eval_count,
                                        "eval_duration": eval_duration,
                                        "prompt_eval_duration": prompt_eval_duration,
                                        "total_duration": total_duration,
                                        "load_duration": load_duration,
                                        "tokens_sec": tokens_sec
                                    }
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode Ollama JSON line: {line}")
                            continue
            except httpx.RequestError as e:
                logger.error(f"Connection to Ollama failed: {e}")
                yield {"type": "error", "content": f"Connection to Ollama failed: {e}"}

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        keep_alive: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Non-streaming generation from Ollama. Returns structured dictionary with 
        full 'thinking' and 'response' text.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive or self.keep_alive,
        }
        if system:
            payload["system"] = system
        
        payload["options"] = self._with_runtime_options(options)

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(f"Ollama returned error: {response.text}")
                    return {"thinking": "", "response": f"Ollama error: {response.status_code}"}
                
                data = response.json()
                text = data.get("response", "")
                
                # Split thinking and response
                thinking = ""
                main_response = text
                if "<think>" in text:
                    parts = text.split("<think>", 1)
                    before_think = parts[0]
                    if "</think>" in parts[1]:
                        think_parts = parts[1].split("</think>", 1)
                        thinking = think_parts[0]
                        main_response = before_think + think_parts[1]
                    else:
                        thinking = parts[1]
                        main_response = before_think
                
                return {"thinking": thinking.strip(), "response": main_response.strip()}
            except httpx.RequestError as e:
                logger.error(f"Connection to Ollama failed: {e}")
                return {"thinking": "", "response": f"Ollama connection error: {e}"}
