import os
import json
import logging
import asyncio
import time
import httpx
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app_backend.ollama_client import OllamaClient
from app_backend.security import SecuritySandbox
from app_backend.git_manager import GitManager
from app_backend.system_metrics import (
    collect_system_snapshot,
    format_hardware_snapshot_log,
    get_amd_gpu_devices,
    get_cpu_temperature,
    get_ollama_runtime,
    summarize_ollama_runtime,
)
from app_backend.agent_orchestrator import (
    EXECUTION_MODE_STANDARD,
    AgentState,
    complete_execution_timer,
    compiled_graph,
    format_execution_timer_seconds,
    format_workflow_totals,
    normalize_execution_mode,
    pause_execution_timer,
    start_execution_timer,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Root directory for all generated workspaces
WORKSPACES_ROOT = "/mnt/3CD02CEED02CB056/Dev/swe-agent/workspaces"
os.makedirs(WORKSPACES_ROOT, exist_ok=True)
sandbox = SecuritySandbox(WORKSPACES_ROOT)

# Dictionary to track background running tasks for cancellation
running_tasks: Dict[str, asyncio.Task] = {}
fast_start_task: Optional[asyncio.Task] = None
manual_fast_start_tasks: set[asyncio.Task] = set()
STARTUP_FAST_START_DEFAULT = False

def track_running_task(project_id: str, task: asyncio.Task):
    running_tasks[project_id] = task

    def cleanup(done_task: asyncio.Task):
        if running_tasks.get(project_id) is done_task:
            del running_tasks[project_id]

    task.add_done_callback(cleanup)

def rolling_preview(text: str, max_lines: int = 3) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])

class StateTrackingQueue:
    def __init__(self, project_id: str, state: AgentState):
        self.project_id = project_id
        self.state = state
        self.queue = asyncio.Queue()
        self.agent = "Developer Agent" if state.get("plan_approved") else "Planner Agent"
        self.response_text = ""
        self.thinking_text = ""
        self.last_snapshot_at = 0.0

    async def put(self, item: Dict[str, Any]):
        self._update_runtime(item)
        await self.queue.put(item)

    async def get(self):
        return await self.queue.get()

    def _save_runtime(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self.last_snapshot_at < 0.5:
            return
        self.last_snapshot_at = now
        state = load_project_state(self.project_id) or self.state
        state["runtime"] = self.state.get("runtime")
        if self.state.get("files_created"):
            state["files_created"] = self.state.get("files_created", [])
        save_project_state(state)

    def _update_runtime(self, item: Dict[str, Any]):
        event = item.get("event")
        data = item.get("data") or ""
        if event == "status":
            status_text = str(data)
            if "Planner" in status_text:
                self.agent = "Planner Agent"
            elif "Developer" in status_text:
                self.agent = "Developer Agent"
            self.state["runtime"] = {
                "active": True,
                "agent": self.agent,
                "status": status_text,
                "response_preview": rolling_preview(self.response_text),
                "thinking_preview": rolling_preview(self.thinking_text),
                "response_chars": len(self.response_text),
            }
            self._save_runtime(force=True)
        elif event == "token":
            token_type = item.get("type")
            token_data = str(data)
            if token_type == "thinking":
                self.thinking_text += token_data
            elif token_type == "response":
                self.response_text += token_data
            self.state["runtime"] = {
                "active": True,
                "agent": self.agent,
                "status": f"{self.agent} em execução.",
                "response_preview": rolling_preview(self.response_text),
                "thinking_preview": rolling_preview(self.thinking_text),
                "response_chars": len(self.response_text),
            }
            self._save_runtime()
        elif event == "files_changed":
            files = item.get("files") or []
            self.state["files_created"] = files
            self.state["runtime"] = {
                "active": True,
                "agent": self.agent,
                "status": "Arquivos atualizados no workspace.",
                "response_preview": rolling_preview(self.response_text),
                "thinking_preview": rolling_preview(self.thinking_text),
                "response_chars": len(self.response_text),
            }
            self._save_runtime(force=True)
        elif event in {"node_complete", "error"}:
            self.state["runtime"] = {
                "active": False,
                "agent": self.agent,
                "status": "Execução concluída." if event == "node_complete" else str(data),
                "response_preview": rolling_preview(self.response_text),
                "thinking_preview": rolling_preview(self.thinking_text),
                "response_chars": len(self.response_text),
            }
            self._save_runtime(force=True)

def _enabled_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def _split_model_names(raw: str) -> list[str]:
    return [model.strip() for model in raw.split(",") if model.strip()]

def _dedupe_model_names(model_names: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for model in model_names:
        cleaned = model.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped

def schedule_model_fast_start(model_names: list[str]) -> asyncio.Task:
    task = asyncio.create_task(fast_start_requested_models(model_names))
    manual_fast_start_tasks.add(task)
    task.add_done_callback(manual_fast_start_tasks.discard)
    return task

async def fast_start_models():
    """
    Touches only the default Planner/Developer models in the background.
    This keeps application startup responsive and avoids loading every Ollama tag.
    """
    from app_backend.agent_orchestrator import (
        DEFAULT_DEVELOPER_MODEL,
        DEFAULT_PLANNER_MODEL,
    )

    if not _enabled_env("SWE_AGENT_FAST_START", STARTUP_FAST_START_DEFAULT):
        logger.info("Fast Start disabled by SWE_AGENT_FAST_START.")
        return

    requested_models = _split_model_names(os.getenv("SWE_AGENT_FAST_START_MODELS", ""))
    if not requested_models:
        requested_models = [DEFAULT_PLANNER_MODEL, DEFAULT_DEVELOPER_MODEL]

    await fast_start_requested_models(requested_models)

async def fast_start_requested_models(requested_models: list[str]) -> list[str]:
    from app_backend.agent_orchestrator import (
        get_available_models,
        resolve_model,
        PLANNER_RUNTIME_OPTIONS,
        DEVELOPER_RUNTIME_OPTIONS,
    )

    requested_models = _dedupe_model_names(requested_models)
    ollama = OllamaClient()
    try:
        available = await get_available_models()
    except Exception as e:
        logger.warning(f"Could not query Ollama models for Fast Start: {e}")
        available = []

    models_to_touch = []
    seen_models = set()
    for model in requested_models:
        resolved = resolve_model(model, available) or model
        if resolved not in seen_models:
            seen_models.add(resolved)
            models_to_touch.append((model, resolved))

    if not models_to_touch:
        logger.info("Fast Start skipped because no models were configured.")
        return []

    logger.info(
        "Fast Start touching %s with keep_alive=%s and use_mmap=%s",
        ", ".join([resolved for _, resolved in models_to_touch]),
        ollama.keep_alive,
        ollama.use_mmap,
    )
    for raw_name, resolved in models_to_touch:
        try:
            options = None
            raw_lower = raw_name.lower()
            resolved_lower = resolved.lower()
            if "planner" in raw_lower or "llama" in raw_lower or "planner" in resolved_lower or "llama" in resolved_lower:
                options = PLANNER_RUNTIME_OPTIONS
            elif "developer" in raw_lower or "coder" in raw_lower or "qwen" in raw_lower or "developer" in resolved_lower or "coder" in resolved_lower or "qwen" in resolved_lower:
                options = DEVELOPER_RUNTIME_OPTIONS
            
            await ollama.fast_start_model(resolved, options=options)
        except Exception as e:
            logger.warning(f"Fast Start failed for model {resolved}: {e}")
    return [resolved for _, resolved in models_to_touch]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the startup and shutdown lifecycle of the FastAPI application."""
    global fast_start_task
    fast_start_task = asyncio.create_task(fast_start_models())
    yield
    if fast_start_task and not fast_start_task.done():
        fast_start_task.cancel()
        try:
            await fast_start_task
        except asyncio.CancelledError:
            pass
    for task in list(manual_fast_start_tasks):
        if not task.done():
            task.cancel()
    if manual_fast_start_tasks:
        await asyncio.gather(*manual_fast_start_tasks, return_exceptions=True)
        manual_fast_start_tasks.clear()

app = FastAPI(title="SWE Local Agent Backend", lifespan=lifespan)

# Enable CORS for Streamlit frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InitPayload(BaseModel):
    project_id: str

class PromptPayload(BaseModel):
    project_id: str
    prompt: str
    feedback: Optional[str] = None
    model_planner: Optional[str] = None
    model_developer: Optional[str] = None
    execution_mode: Optional[str] = None

class ApprovePayload(BaseModel):
    project_id: str
    model_planner: Optional[str] = None
    model_developer: Optional[str] = None
    execution_mode: Optional[str] = None

class FastStartPayload(BaseModel):
    model_planner: Optional[str] = None
    model_developer: Optional[str] = None
    models: Optional[list[str]] = None

class RollbackPayload(BaseModel):
    project_id: str
    sha: str

def get_state_file_path(project_id: str) -> Path:
    project_dir = sandbox.validate_path(project_id, ".")
    return project_dir / ".swe_local_agent" / "state.json"

def load_project_state(project_id: str) -> Optional[AgentState]:
    """
    Safely retrieves the state.json of a project, returning a dictionary representing AgentState.
    """
    try:
        project_dir = sandbox.validate_path(project_id, ".")
        if project_dir.exists() and project_dir.is_dir():
            GitManager.remove_legacy_workspace_readme(project_dir)
        path = get_state_file_path(project_id)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                
                state: AgentState = {
                    "project_id": project_id,
                    "prompt": state_data.get("prompt", ""),
                    "plan_version": state_data.get("plan_version", "1.0"),
                    "plan_content": state_data.get("plan_content", ""),
                    "user_feedback": state_data.get("user_feedback"),
                    "plan_approved": state_data.get("plan_approved", False),
                    "current_step": state_data.get("current_step", "planning"),
                    "errors": state_data.get("errors", []),
                    "files_created": state_data.get("files_created", []),
                    "self_healing_attempts": state_data.get("self_healing_attempts", 0),
                    "log_messages": state_data.get("log_messages", []),
                    "model_planner": state_data.get("model_planner"),
                    "model_developer": state_data.get("model_developer"),
                    "execution_mode": normalize_execution_mode(state_data.get("execution_mode")),
                    "execution_timer": state_data.get("execution_timer"),
                    "metrics": state_data.get("metrics", []),
                    "runtime": state_data.get("runtime"),
                    "hardware_snapshots": state_data.get("hardware_snapshots", []),
                    "quality_checks": state_data.get("quality_checks", {}),
                }
                if "test_results" in state_data:
                    state["test_results"] = state_data.get("test_results")
                return state
        else:
            # If the workspace folder exists, auto-initialize it with a default state
            if project_dir.exists() and project_dir.is_dir():
                default_state = {
                    "project_id": project_id,
                    "prompt": "",
                    "plan_version": "1.0",
                    "plan_content": "",
                    "user_feedback": None,
                    "plan_approved": False,
                    "current_step": "planning",
                    "errors": [],
                    "files_created": [],
                    "self_healing_attempts": 0,
                    "log_messages": [],
                    "model_planner": None,
                    "model_developer": None,
                    "execution_mode": EXECUTION_MODE_STANDARD,
                    "execution_timer": None,
                    "metrics": [],
                    "runtime": None,
                    "hardware_snapshots": [],
                    "quality_checks": {},
                }
                save_project_state(default_state)
                return default_state
    except Exception as e:
        logger.error(f"Error loading project state for {project_id}: {e}")
    return None

def save_project_state(state: AgentState):
    """
    Saves the state.json file of a project within its respective workspace directory.
    """
    try:
        project_id = state["project_id"]
        project_dir = sandbox.validate_path(project_id, ".")
        state_dir = project_dir / ".swe_local_agent"
        state_dir.mkdir(exist_ok=True)
        path = state_dir / "state.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving project state: {e}")

async def append_hardware_snapshot(state: AgentState, label: str) -> Dict[str, Any]:
    snapshot = await collect_system_snapshot(label)
    snapshots = list(state.get("hardware_snapshots", []))
    snapshots.append(snapshot)
    state["hardware_snapshots"] = snapshots[-24:]

    log_messages = list(state.get("log_messages", []))
    log_messages.append(format_hardware_snapshot_log(snapshot))
    state["log_messages"] = log_messages
    return snapshot

async def run_graph_in_background(state: AgentState, queue: asyncio.Queue):
    """
    Invokes the compiled LangGraph in a background task, sharing a thread-safe asyncio.Queue.
    """
    from app_backend.agent_orchestrator import get_available_models, resolve_model, DEFAULT_PLANNER_MODEL, DEFAULT_DEVELOPER_MODEL
    ollama = OllamaClient()
    # Resolve models once, not in each node
    available = await get_available_models()
    resolved_planner = resolve_model(state.get("model_planner") or DEFAULT_PLANNER_MODEL, available) or DEFAULT_PLANNER_MODEL
    resolved_developer = resolve_model(state.get("model_developer") or DEFAULT_DEVELOPER_MODEL, available) or DEFAULT_DEVELOPER_MODEL
    try:
        config = {
            "configurable": {
                "queue": queue,
                "sandbox": sandbox,
                "ollama": ollama,
                "model_planner": resolved_planner,
                "model_developer": resolved_developer,
                "models_resolved": True
            }
        }
        final_state = await compiled_graph.ainvoke(state, config=config)
        log_messages = list(final_state.get("log_messages", []))
        if final_state.get("current_step") == "planning" and not final_state.get("plan_approved"):
            timer_data = pause_execution_timer(final_state)
            timer_msg = f"Timer de execução pausado no plano: {format_execution_timer_seconds(timer_data)}."
            if timer_msg not in log_messages:
                log_messages.append(timer_msg)
            final_state["log_messages"] = log_messages
            await append_hardware_snapshot(final_state, "planner_end")
            await queue.put({"event": "status", "data": timer_msg})
        elif final_state.get("current_step") in {"completed", "failed"}:
            timer_data = complete_execution_timer(final_state)
            timer_msg = f"Timer de execução finalizado: {format_execution_timer_seconds(timer_data)}."
            if timer_msg not in log_messages:
                log_messages.append(timer_msg)
            final_state["log_messages"] = log_messages
            await append_hardware_snapshot(final_state, "developer_end")
            await queue.put({"event": "status", "data": timer_msg})

        workflow_summary = format_workflow_totals(final_state.get("metrics", []))
        if workflow_summary:
            log_messages = list(final_state.get("log_messages", []))
            if workflow_summary not in log_messages:
                log_messages.append(workflow_summary)
            final_state["log_messages"] = log_messages
            await queue.put({"event": "status", "data": workflow_summary})
        save_project_state(final_state)
        # Signal files changed so frontend can refresh the explorer
        await queue.put({"event": "files_changed", "files": final_state.get("files_created", [])})
        await queue.put({"event": "node_complete", "state": final_state})
    except asyncio.CancelledError:
        logger.info(f"Task for project {state['project_id']} was cancelled.")
        # Even on cancel, save current state so frontend can recover
        timer_data = pause_execution_timer(state)
        log_messages = list(state.get("log_messages", []))
        log_messages.append(f"Timer de execução pausado no cancelamento: {format_execution_timer_seconds(timer_data)}.")
        state["log_messages"] = log_messages
        save_project_state(state)
        await queue.put({"event": "status", "data": "Cancelado: Execução interrompida pelo usuário."})
        await queue.put({"event": "error", "data": "Execução cancelada."})
    except Exception as e:
        logger.exception("Error executing compiled state graph")
        timer_data = complete_execution_timer(state)
        log_messages = list(state.get("log_messages", []))
        log_messages.append(f"Timer de execução finalizado com erro: {format_execution_timer_seconds(timer_data)}.")
        state["log_messages"] = log_messages
        save_project_state(state)
        await queue.put({"event": "error", "data": str(e)})

@app.post("/api/project/init")
async def init_project(payload: InitPayload):
    try:
        project_dir = sandbox.validate_path(payload.project_id, ".")
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Git Repo initialization
        GitManager.init_repo(project_dir)
        GitManager.remove_legacy_workspace_readme(project_dir)
        
        # Save fresh initial state structure
        state: AgentState = {
            "project_id": payload.project_id,
            "prompt": "",
            "plan_version": "1.0",
            "plan_content": "",
            "user_feedback": None,
            "plan_approved": False,
            "current_step": "planning",
            "errors": [],
            "files_created": [],
            "self_healing_attempts": 0,
            "log_messages": ["Workspace criado e inicializado."],
            "model_planner": None,
            "model_developer": None,
            "execution_mode": EXECUTION_MODE_STANDARD,
            "execution_timer": None,
            "metrics": [],
            "runtime": None,
            "hardware_snapshots": [],
            "quality_checks": {},
        }
        save_project_state(state)
        return {"status": "success", "message": f"Workspace {payload.project_id} configurado."}
    except Exception as e:
        logger.error(f"Error initializing workspace: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/prompt")
async def run_prompt(payload: PromptPayload):
    """
    Triggers the Planner Agent to generate or edit implementation_plan.md.
    """
    try:
        state = load_project_state(payload.project_id)
        if not state:
            state = {
                "project_id": payload.project_id,
                "prompt": payload.prompt,
                "plan_version": "1.0",
                "plan_content": "",
                "user_feedback": payload.feedback,
                "plan_approved": False,
                "current_step": "planning",
                "errors": [],
                "files_created": [],
                "self_healing_attempts": 0,
                "log_messages": [],
                "model_planner": payload.model_planner,
                "model_developer": payload.model_developer,
                "execution_mode": EXECUTION_MODE_STANDARD,
                "execution_timer": None,
                "metrics": [],
                "runtime": None,
                "hardware_snapshots": [],
                "quality_checks": {},
            }
        else:
            if payload.prompt:
                state["prompt"] = payload.prompt
            if payload.feedback:
                state["user_feedback"] = payload.feedback
            if payload.model_planner:
                state["model_planner"] = payload.model_planner
            if payload.model_developer:
                state["model_developer"] = payload.model_developer
            state["execution_mode"] = EXECUTION_MODE_STANDARD

        state["plan_approved"] = False
        state["current_step"] = "planning"
        state["errors"] = []
        state["metrics"] = []
        state["hardware_snapshots"] = []
        state["quality_checks"] = {}
        state["runtime"] = {
            "active": True,
            "agent": "Planner Agent",
            "status": "Preparando Planner Agent.",
            "response_preview": "",
            "thinking_preview": "",
            "response_chars": 0,
        }
        start_execution_timer(state, reset=not bool(payload.feedback), phase="planner")
        await append_hardware_snapshot(state, "planner_start")
        save_project_state(state)

        # Cancel any previous running task for this project
        if payload.project_id in running_tasks:
            try:
                running_tasks[payload.project_id].cancel()
            except Exception:
                pass

        queue = StateTrackingQueue(payload.project_id, state)
        task = asyncio.create_task(run_graph_in_background(state, queue))
        track_running_task(payload.project_id, task)

        async def event_generator():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=600.0)
                        yield f"data: {json.dumps(item)}\n\n"
                        if item.get("event") in ["node_complete", "error"]:
                            break
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'event': 'error', 'data': 'Timeout no backend durante o planejamento.'})}\n\n"
                        break
            finally:
                if task.done() and payload.project_id in running_tasks and running_tasks[payload.project_id] == task:
                    del running_tasks[payload.project_id]

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in prompt execution: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/approve")
async def approve_project(payload: ApprovePayload):
    """
    Confirms planning, triggering developer & testing loops.
    """
    try:
        state = load_project_state(payload.project_id)
        if not state:
            raise HTTPException(status_code=404, detail="Projeto não encontrado.")
        if not state.get("plan_content", "").strip():
            raise HTTPException(
                status_code=400,
                detail="Plano de implementação vazio. Gere ou ajuste o plano antes de aprovar para codificação."
            )

        state["plan_approved"] = True
        state["user_feedback"] = None
        state["self_healing_attempts"] = 0
        state["errors"] = []
        state["current_step"] = "coding"
        state["runtime"] = {
            "active": True,
            "agent": "Developer Agent",
            "status": "Preparando Developer Agent.",
            "response_preview": "",
            "thinking_preview": "",
            "response_chars": 0,
        }
        log_messages = list(state.get("log_messages", []))
        log_messages.append("Plano aprovado. Iniciando Developer Agent.")
        state["log_messages"] = log_messages
        if payload.model_planner:
            state["model_planner"] = payload.model_planner
        if payload.model_developer:
            state["model_developer"] = payload.model_developer
        state["execution_mode"] = EXECUTION_MODE_STANDARD

        start_execution_timer(state, reset=False, phase="developer")
        await append_hardware_snapshot(state, "developer_start")
        save_project_state(state)

        # Cancel any previous running task for this project
        if payload.project_id in running_tasks:
            try:
                running_tasks[payload.project_id].cancel()
            except Exception:
                pass

        queue = StateTrackingQueue(payload.project_id, state)
        task = asyncio.create_task(run_graph_in_background(state, queue))
        track_running_task(payload.project_id, task)

        async def event_generator():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=600.0)
                        yield f"data: {json.dumps(item)}\n\n"
                        if item.get("event") in ["node_complete", "error"]:
                            break
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'event': 'error', 'data': 'Timeout no backend durante desenvolvimento.'})}\n\n"
                        break
            finally:
                if task.done() and payload.project_id in running_tasks and running_tasks[payload.project_id] == task:
                    del running_tasks[payload.project_id]

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in project approval: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/stop")
async def stop_project(payload: InitPayload):
    """
    Interrupts/cancels the running background task for the specified project.
    """
    if payload.project_id in running_tasks:
        task = running_tasks[payload.project_id]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if payload.project_id in running_tasks:
            del running_tasks[payload.project_id]
        return {"status": "success", "message": "Execução cancelada com sucesso."}
    return {"status": "success", "message": "Nenhum agente em execução para este workspace."}

@app.get("/api/system/models")
async def get_models():
    """
    Queries local Ollama tags to fetch available models.
    """
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                models_data = r.json()
                models = [m["name"] for m in models_data.get("models", [])]
                if models:
                    return {"models": sorted(models)}
    except Exception as e:
        logger.warning(f"Failed to query Ollama models: {e}")
    
    # Standard fallbacks if unreachable/empty
    return {"models": ["llama3.2-3b-local", "qwen2.5-coder-7b-local", "qwen2.5-coder-3b-local"]}

@app.post("/api/system/fast-start")
async def fast_start_selected_models(payload: FastStartPayload):
    """
    Schedules a non-blocking Fast Start for models selected at runtime in the GUI.
    """
    requested_models = list(payload.models or [])
    if payload.model_planner:
        requested_models.append(payload.model_planner)
    if payload.model_developer:
        requested_models.append(payload.model_developer)

    requested_models = _dedupe_model_names(requested_models)
    if not requested_models:
        raise HTTPException(status_code=400, detail="Informe ao menos um modelo para Fast Start.")

    client = OllamaClient()
    schedule_model_fast_start(requested_models)
    return {
        "status": "scheduled",
        "models": requested_models,
        "keep_alive": client.keep_alive,
        "use_mmap": client.use_mmap,
    }

@app.get("/api/project/status/{project_id}")
async def get_status(project_id: str):
    state = load_project_state(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return state

@app.get("/api/project/history/{project_id}")
async def get_history(project_id: str):
    try:
        project_dir = sandbox.validate_path(project_id, ".")
        history = GitManager.get_history(project_dir)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error fetching git history: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/rollback")
async def rollback_project(payload: RollbackPayload):
    try:
        project_dir = sandbox.validate_path(payload.project_id, ".")
        
        # Hard rollback and clean untracked files
        GitManager.rollback(project_dir, payload.sha)
        
        # Load state restored from the older git commit
        state = load_project_state(payload.project_id)
        if not state:
            raise HTTPException(status_code=400, detail="Rollback concluído, mas falhou ao restabelecer state.json.")

        return {"status": "success", "state": state}
    except Exception as e:
        logger.error(f"Error rolling back project: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/system/metrics")
async def get_metrics():
    try:
        return await collect_system_snapshot("live")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
