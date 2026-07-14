import os
import json
import html
import re
import time
import httpx
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

# Configure Streamlit page layout and theme
st.set_page_config(
    page_title="SWE Local Agent IDE",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed"
)

BACKEND_URL = "http://127.0.0.1:8000"
WORKSPACES_ROOT = Path("/mnt/3CD02CEED02CB056/Dev/swe-agent/workspaces")
WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)

# Custom styling for a premium dark mode, glassmorphism elements, and reasoning box
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&display=swap');

html, body, [class*="css"], .stApp, .stTextInput, .stSelectbox, .stButton, div, span, p, h1, h2, h3, h4, h5, h6 {
    font-family: 'JetBrains Mono', monospace !important;
}

.stApp {
    background-color: #07080a !important;
    color: #c9d1d9 !important;
}

/* Hide Streamlit default frames & headers */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
[data-testid="stHeader"] {
    display: none !important;
}

/* Hide all default Streamlit chat avatars to prevent text fallbacks */
[data-testid="stChatMessageAvatar"],
[data-testid="chatAvatar"],
.st-emotion-cache-12m1z1c,
.st-emotion-cache-kd8x8a,
div[data-testid="stChatMessage"] > div:first-child {
    display: none !important;
    width: 0px !important;
    height: 0px !important;
    margin: 0px !important;
    padding: 0px !important;
    visibility: hidden !important;
}

/* Make chat message content expand to 100% width since avatar is hidden */
div[data-testid="stChatMessageContent"] {
    width: 100% !important;
    padding: 0px !important;
    margin: 0px !important;
}

/* Style all chat message bubbles as premium unified dark cards */
div[data-testid="stChatMessage"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
    margin-bottom: 8px !important;
}

/* Give user messages a distinct dark blue tint border */
div[data-testid="stChatMessage"][data-chat-message-user="true"],
div[data-testid="stChatMessage"]:has(div[data-testid="chat-message-user"]) {
    background-color: #1c212a !important;
    border-color: #388bfd !important;
}

.user-chat-card {
    background: linear-gradient(180deg, #07111f 0%, #0b1324 100%);
    border: 1px solid #2f81f7;
    box-shadow: 0 0 14px rgba(47, 129, 247, 0.42);
    border-radius: 6px;
    padding: 10px 12px;
    margin: 0 0 10px 0;
    color: #e6edf3;
    font-size: 12px;
    line-height: 1.55;
}

.user-chat-label {
    color: #79c0ff;
    font-weight: 700;
    margin-bottom: 4px;
}

/* High contrast white-gray text colors for readability */
div[data-testid="stChatMessage"] p, 
div[data-testid="stChatMessage"] li, 
div[data-testid="stChatMessage"] span,
div[data-testid="stChatMessage"] div,
div[data-testid="stChatMessage"] strong {
    color: #e6edf3 !important;
}

div[data-testid="stChatMessage"] pre,
div[data-testid="stChatMessage"] code,
div[data-testid="stMarkdownContainer"] pre,
div[data-testid="stMarkdownContainer"] code,
div[data-testid="stCodeBlock"],
div[data-testid="stCodeBlock"] pre {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
    border-color: #30363d !important;
}

div[data-testid="stChatMessage"] code {
    color: #79c0ff !important;
}

/* Base block container style to fit screen - Override Streamlit default 6rem top padding */
div[data-testid="stMainBlockContainer"] {
    max-height: 100vh !important;
    overflow-y: hidden !important;
    padding-top: 5px !important;
    padding-bottom: 25px !important;
    padding-left: 15px !important;
    padding-right: 15px !important;
}

/* Scroll constraints for columns - Allow scrolling if elements overflow */
div[data-testid="column"] {
    max-height: calc(100vh - 30px) !important;
    overflow-y: auto !important;
    padding: 5px !important;
}

/* Fixed status bar footer */
.footer-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 24px;
    background-color: #0d1117;
    border-top: 1px solid #21262d;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    font-size: 11px;
    color: #8b949e;
    z-index: 999999;
}
.footer-bar .status-online {
    color: #58a6ff;
    font-weight: bold;
}
.footer-bar .status-offline {
    color: #f85149;
    font-weight: bold;
}
.footer-bar .footer-metric {
    color: #58a6ff;
    font-weight: bold;
}

/* Global button styling - premium dark buttons with readable text */
.stButton button, div[data-testid="column"] button {
    background-color: #21262d !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    font-family: 'JetBrains Mono', monospace !important;
    box-shadow: none !important;
    text-shadow: none !important;
}
.stButton button:hover, div[data-testid="column"] button:hover {
    background-color: #30363d !important;
    border-color: #8b949e !important;
    color: #ffffff !important;
}

/* File explorer buttons styling to look like tree list items */
div[data-testid="column"]:nth-of-type(1) .stButton button {
    text-align: left !important;
    justify-content: flex-start !important;
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    padding: 4px 8px !important;
    font-size: 11px !important;
    margin: 1px 0 !important;
    border-radius: 3px !important;
    box-shadow: none !important;
    display: flex !important;
    width: 100% !important;
}
div[data-testid="column"]:nth-of-type(1) .stButton button:hover {
    background-color: #21262d !important;
    border-color: #8b949e !important;
    color: #ffffff !important;
}

/* Welcome interface styling */
.welcome-card {
    padding: 20px;
    background-color: #0d1117;
    border: 1px solid #21262d;
    margin-top: 10px;
}

/* Reasoning block - compact 3-line rolling preview */
.reasoning-box {
    background-color: #161b22;
    border-left: 3px solid #ff7b72;
    padding: 8px 10px;
    margin-bottom: 8px;
    font-size: 11px;
    color: #8b949e;
    max-height: 72px;
    overflow: hidden;
    border-radius: 4px;
    line-height: 1.55;
}

.agent-loading-card {
    display: flex;
    align-items: center;
    gap: 10px;
    background-color: #0d1117;
    border-left: 3px solid #58a6ff;
    padding: 8px 10px;
    border-radius: 4px;
    color: #c9d1d9;
    font-size: 11px;
    line-height: 1.55;
}

.agent-loading-spinner {
    width: 14px;
    height: 14px;
    border: 2px solid #30363d;
    border-top-color: #58a6ff;
    border-radius: 50%;
    flex: 0 0 auto;
    animation: agent-spin 0.8s linear infinite;
}

.agent-loading-dots::after {
    content: "";
    animation: agent-dots 1.2s steps(4, end) infinite;
}

@keyframes agent-spin {
    to { transform: rotate(360deg); }
}

@keyframes agent-dots {
    0% { content: ""; }
    25% { content: "."; }
    50% { content: ".."; }
    75% { content: "..."; }
    100% { content: ""; }
}

.reasoning-box::-webkit-scrollbar {
    width: 8px;
}

.reasoning-box::-webkit-scrollbar-thumb {
    background-color: #30363d;
    border-radius: 8px;
}

/* Custom compact button overrides for columns 2 and 3 */
div[data-testid="column"] button {
    margin-top: 0px !important;
    margin-bottom: 0px !important;
    padding: 2px 4px !important;
    font-size: 11px !important;
}

/* Chat input: keep multiline prompts readable and use the available box area */
div[data-testid="stChatInput"] {
    padding-bottom: 12px !important;
    padding-top: 5px !important;
}
div[data-testid="stChatInput"] textarea {
    font-size: 12px !important;
    height: 92px !important;
    min-height: 92px !important;
    max-height: 150px !important;
    padding: 10px 44px 10px 12px !important;
    line-height: 1.4 !important;
    color: #0f1419 !important;
    overflow-y: auto !important;
    resize: vertical !important;
}
div[data-testid="stChatInput"] textarea::placeholder {
    color: #5c6370 !important;
}

div[data-testid="stTextArea"] textarea {
    background-color: #e6edf3 !important;
    color: #0d1117 !important;
    border: 1px solid #30363d !important;
    caret-color: #0d1117 !important;
    box-shadow: none !important;
    font-family: 'JetBrains Mono', monospace !important;
}

div[data-testid="stTextArea"] textarea:focus {
    border-color: #2f81f7 !important;
    box-shadow: 0 0 0 1px rgba(47, 129, 247, 0.35) !important;
}

div[data-testid="stTextArea"] textarea::placeholder {
    color: #4b5563 !important;
    opacity: 1 !important;
}
/* Complete fix for the expander icon text overlap */
[data-testid="stExpander"] summary > * > *:first-child,
[data-testid="stExpander"] details > summary > * > *:first-child,
[data-testid="stExpander"] summary svg,
[data-testid="stExpander"] details > summary svg,
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    visibility: hidden !important;
}
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE INIT -----------------
if "project_id" not in st.session_state:
    st.session_state.project_id = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None
if "file_content" not in st.session_state:
    st.session_state.file_content = None
if "state" not in st.session_state:
    st.session_state.state = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "console_logs" not in st.session_state:
    st.session_state.console_logs = []
if "show_new_ws" not in st.session_state:
    st.session_state.show_new_ws = False
if "available_models" not in st.session_state:
    st.session_state.available_models = []
if "pending_agent_flow" not in st.session_state:
    st.session_state.pending_agent_flow = None
if "execution_mode" not in st.session_state:
    st.session_state.execution_mode = "standard"
if "file_explorer_render_nonce" not in st.session_state:
    st.session_state.file_explorer_render_nonce = 0
if "last_fast_start_models" not in st.session_state:
    st.session_state.last_fast_start_models = None

# ----------------- BACKEND API HELPERS -----------------
def check_backend() -> bool:
    try:
        r = httpx.get(f"{BACKEND_URL}/api/system/metrics", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

def get_system_metrics():
    try:
        r = httpx.get(f"{BACKEND_URL}/api/system/metrics", timeout=1.5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def fetch_available_models():
    try:
        r = httpx.get(f"{BACKEND_URL}/api/system/models", timeout=2.0)
        if r.status_code == 200:
            return r.json().get("models", [])
    except Exception:
        pass
    return ["llama3.2-3b-local", "qwen2.5-coder-7b-local", "qwen2.5-coder-3b-local"]

def request_fast_start_models(model_planner, model_developer):
    selected_models = tuple(model for model in [model_planner, model_developer] if model)
    if not selected_models or st.session_state.last_fast_start_models == selected_models:
        return
    try:
        r = httpx.post(
            f"{BACKEND_URL}/api/system/fast-start",
            json={
                "model_planner": model_planner,
                "model_developer": model_developer,
            },
            timeout=2.0,
        )
        if r.status_code == 200:
            st.session_state.last_fast_start_models = selected_models
    except Exception:
        pass

def rebuild_chat_history_from_state(state):
    history = []
    if not state:
        return history
    
    # 1. User Prompt
    if state.get("prompt"):
        history.append({
            "role": "user",
            "content": state["prompt"]
        })
        
    # 2. Plan notification
    if state.get("plan_content"):
        history.append({
            "role": "assistant",
            "agent": "Planner Agent",
            "content": plan_ready_message(state.get("plan_version", "1.0"))
        })

    if state.get("plan_approved"):
        history.append({
            "role": "user",
            "content": "Plano de implementação aprovado. Pode iniciar a codificação."
        })

    current = state.get("current_step")
    if current == "coding":
        runtime = state.get("runtime") or {}
        preview = runtime.get("response_preview") or runtime.get("status") or "Developer Agent em execução."
        history.append({
            "role": "assistant",
            "agent": runtime.get("agent") or "Developer Agent",
            "content": (
                "Desenvolvimento em andamento. Acompanhe os arquivos na área **Arquivos** à esquerda.\n\n"
                f"```text\n{preview}\n```"
            )
        })
    elif current == "completed":
        history.append({
            "role": "assistant",
            "agent": "Developer Agent",
            "content": success_completion_message(state.get("files_created", []))
        })
    elif current == "failed":
        errors = state.get("errors") or []
        error_lines = "\n".join(f"- {error}" for error in errors) if errors else "- O agente não conseguiu concluir a entrega."
        history.append({
            "role": "assistant",
            "agent": "Developer Agent",
            "content": f"Fluxo encerrado antes da conclusão.\n\n{error_lines}\n\nVeja os detalhes no log de execução."
        })
        
    return history

def chat_message_key(msg):
    return (
        msg.get("role"),
        msg.get("agent"),
        msg.get("content"),
    )

def merge_chat_history(existing, rebuilt):
    merged = list(existing or [])
    seen = {chat_message_key(msg) for msg in merged}
    for msg in rebuilt or []:
        key = chat_message_key(msg)
        if key not in seen:
            merged.append(msg)
            seen.add(key)
    return merged

def fetch_project_state(project_id: str, preserve_chat: bool = False):
    try:
        r = httpx.get(f"{BACKEND_URL}/api/project/status/{project_id}")
        if r.status_code == 200:
            previous_chat = list(st.session_state.chat_history or [])
            st.session_state.state = r.json()
            st.session_state.console_logs = st.session_state.state.get("log_messages", [])
            rebuilt_chat = rebuild_chat_history_from_state(st.session_state.state)
            st.session_state.chat_history = (
                merge_chat_history(previous_chat, rebuilt_chat)
                if preserve_chat
                else rebuilt_chat
            )
            timer = st.session_state.state.get("execution_timer") or {}
            if (
                st.session_state.state.get("current_step") in {"completed", "failed"}
                or timer.get("status") in {"completed", "paused"}
            ):
                st.session_state.is_running = False
                st.session_state.pending_agent_flow = None
    except Exception as e:
        st.error(f"Erro ao buscar estado do projeto: {e}")

def stop_agent_execution(project_id: str):
    try:
        httpx.post(f"{BACKEND_URL}/api/project/stop", json={"project_id": project_id})
        st.session_state.is_running = False
        st.toast("Comando para parar enviado.")
    except Exception as e:
        st.error(f"Erro ao parar agente: {e}")

def mark_local_timer_running(phase: str, reset: bool = False):
    if not st.session_state.state:
        return

    now = time.time()
    timer = st.session_state.state.get("execution_timer") or {}
    phases = timer.get("phase_seconds") or {"planner": 0.0, "developer": 0.0}
    if reset:
        phases = {"planner": 0.0, "developer": 0.0}
    st.session_state.state["execution_timer"] = {
        "status": "running",
        "current_phase": phase,
        "phase_seconds": {
            "planner": float(phases.get("planner") or 0.0),
            "developer": float(phases.get("developer") or 0.0),
        },
        "accumulated_seconds": float(phases.get("planner") or 0.0) + float(phases.get("developer") or 0.0),
        "segment_started_at": now,
    }

def queue_agent_flow(payload, endpoint):
    if endpoint == "/api/project/approve":
        mark_local_timer_running("developer", reset=False)
    elif endpoint == "/api/project/prompt":
        mark_local_timer_running("planner", reset=not bool(payload.get("feedback")))

    st.session_state.pending_agent_flow = {
        "payload": payload,
        "endpoint": endpoint
    }
    st.rerun()

def queue_approval_flow(payload):
    if st.session_state.state:
        st.session_state.state["plan_approved"] = True
        st.session_state.state["current_step"] = "coding"
    approval_message = "Plano de implementação aprovado. Pode iniciar a codificação."
    last_message = st.session_state.chat_history[-1]["content"] if st.session_state.chat_history else ""
    if last_message != approval_message:
        st.session_state.chat_history.append({
            "role": "user",
            "content": approval_message
        })
    st.session_state.console_logs.append("Plano aprovado. Iniciando Developer Agent...")
    queue_agent_flow(payload, "/api/project/approve")

def model_match_tokens(model_name):
    ignored_tokens = {"latest", "local", "planner", "developer"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (model_name or "").lower())
        if token not in ignored_tokens
    }

def choose_model(saved_model, preferred_model, models_list):
    if saved_model in models_list:
        return saved_model
    if preferred_model in models_list:
        return preferred_model
    preferred_latest = f"{preferred_model}:latest"
    if preferred_latest in models_list:
        return preferred_latest
    for model in models_list:
        if preferred_model.lower() in model.lower():
            return model
    preferred_tokens = model_match_tokens(preferred_model)
    for model in models_list:
        if preferred_tokens and preferred_tokens.issubset(model_match_tokens(model)):
            return model
    return models_list[0] if models_list else ""

def plan_ready_message(version="1.0"):
    return (
        f"Plano de implementação v{version} concluído e salvo em `implementation_plan.md`.\n\n"
        "Revise o arquivo pelo painel **Arquivos** à esquerda. Se estiver correto, use **Aprovar e Codificar**; "
        "se precisar de mudanças, descreva o ajuste no campo de feedback e clique em **Ajustar Plano**."
    )

def normalize_log_entries(logs):
    if isinstance(logs, str):
        source_logs = [logs]
    else:
        source_logs = logs or []

    entries = []
    for raw_log in source_logs:
        raw_text = str(raw_log).strip()
        if not raw_text:
            continue
        raw_text = re.sub(
            r"\s+-\s+(?=(?:Workspace|Planner Agent|Developer Agent|Workflow|Timer|Iniciando|Plano|Modo|Escrito|Aviso|Erro|Codex|Project Manager|Avaliação|Cancelado|Resultado))",
            "\n",
            raw_text,
        )
        for line in raw_text.splitlines():
            log = re.sub(r"^\s*-\s*", "", line).strip()
            if log and log not in entries:
                entries.append(log)
    return entries

def metric_for_agent(metrics, agent_name):
    for metric in reversed(metrics or []):
        if isinstance(metric, dict) and metric.get("agent") == agent_name:
            return metric
    return None

def extract_agent_model(entries, agent_name, fallback=None):
    pattern = re.compile(rf"Iniciando {re.escape(agent_name)} \((.*?)\)")
    for entry in entries:
        match = pattern.search(entry)
        if match:
            return match.group(1)
    return fallback

def extract_written_files(entries, state=None):
    files = []
    for entry in entries:
        if entry.startswith("Escrito: "):
            filepath = entry.replace("Escrito: ", "", 1).strip()
            if filepath and filepath not in files:
                files.append(filepath)
    for filepath in (state or {}).get("files_created", []) or []:
        if filepath and filepath not in files:
            files.append(filepath)
    return files

def append_metric_lines(lines, metric):
    if not metric:
        lines.append("   - Métricas: ainda não disponíveis.")
        return

    lines.extend([
        "   - Métricas:",
        f"     - Tempo: {float(metric.get('duration_seconds') or 0.0):.2f}s",
        f"     - Tokens resposta: {int(metric.get('eval_count') or 0)}",
        f"     - Tokens prompt: {int(metric.get('prompt_eval_count') or 0)}",
        f"     - Média: {float(metric.get('tokens_sec') or 0.0):.1f} TPS",
    ])

def append_workflow_totals(lines, metrics, state=None):
    valid_metrics = [metric for metric in metrics or [] if isinstance(metric, dict)]
    if not valid_metrics:
        return

    timer = (state or {}).get("execution_timer") if state else None
    total_seconds = (
        execution_timer_elapsed(timer)
        if isinstance(timer, dict)
        else sum(float(metric.get("duration_seconds") or 0.0) for metric in valid_metrics)
    )
    output_tokens = sum(int(metric.get("eval_count") or 0) for metric in valid_metrics)
    prompt_tokens = sum(int(metric.get("prompt_eval_count") or 0) for metric in valid_metrics)
    eval_seconds = sum(float(metric.get("eval_duration_seconds") or 0.0) for metric in valid_metrics)
    avg_tps = (output_tokens / eval_seconds) if eval_seconds else 0.0
    totals_label = (
        "Totais do workflow"
        if (state or {}).get("current_step") in {"completed", "failed"}
        else "Totais medidos até agora"
    )

    lines.extend([
        "",
        totals_label,
        f"   - Tempo: {total_seconds:.2f}s",
        f"   - Tokens resposta: {output_tokens}",
        f"   - Tokens prompt: {prompt_tokens}",
        f"   - Média: {avg_tps:.1f} TPS",
    ])

def execution_timer_elapsed(timer):
    if not isinstance(timer, dict):
        return 0.0
    phases = timer.get("phase_seconds") or {}
    if phases:
        accumulated = float(phases.get("planner") or 0.0) + float(phases.get("developer") or 0.0)
    else:
        accumulated = float(timer.get("accumulated_seconds") or 0.0)
    started_at = timer.get("segment_started_at")
    if timer.get("status") == "running" and started_at:
        return max(0.0, accumulated + (time.time() - float(started_at)))
    return max(0.0, accumulated)

def execution_timer_phase_elapsed(timer, phase):
    if not isinstance(timer, dict):
        return 0.0
    phases = timer.get("phase_seconds") or {}
    accumulated = float(phases.get(phase) or 0.0)
    started_at = timer.get("segment_started_at")
    if timer.get("status") == "running" and timer.get("current_phase") == phase and started_at:
        return max(0.0, accumulated + (time.time() - float(started_at)))
    return max(0.0, accumulated)

def append_execution_timer_lines(lines, state):
    timer = state.get("execution_timer") if state else None
    if not isinstance(timer, dict):
        return

    status_labels = {
        "running": "em execução",
        "paused": "pausado",
        "completed": "concluído",
    }
    status = status_labels.get(timer.get("status"), timer.get("status") or "não iniciado")
    lines.extend([
        "",
        "Timer de execução",
        f"   - Status: {status}",
        f"   - Planner Agent: {execution_timer_phase_elapsed(timer, 'planner'):.2f}s",
        f"   - Developer Agent: {execution_timer_phase_elapsed(timer, 'developer'):.2f}s",
        f"   - Total ativo: {execution_timer_elapsed(timer):.2f}s",
    ])

def append_hardware_snapshot_lines(lines, state):
    snapshots = state.get("hardware_snapshots") if state else None
    if not snapshots:
        return

    snapshot = snapshots[-1]
    ollama = snapshot.get("ollama") or {}
    gpu_devices = (snapshot.get("gpu") or {}).get("amd_devices") or []
    label = snapshot.get("label") or "snapshot"
    temp = snapshot.get("cpu_temp")
    temp_text = "N/A" if temp is None else f"{float(temp):.1f}°C"

    lines.extend([
        "",
        "Hardware / Runtime",
        f"   - Último snapshot: {label}",
        f"   - CPU: {float(snapshot.get('cpu_percent') or 0.0):.1f}%",
        f"   - RAM: {float(snapshot.get('ram_used_gb') or 0.0):.2f} GB / {float(snapshot.get('ram_total_gb') or 0.0):.2f} GB",
        f"   - Temperatura: {temp_text}",
        (
            f"   - LLM: {ollama.get('processor', 'N/A')} | "
            f"{float(ollama.get('vram_gb') or 0.0):.2f} GB | "
            f"{ollama.get('memory_label', 'N/A')}"
        ),
    ])

    if gpu_devices:
        memory = (gpu_devices[0] or {}).get("memory") or {}
        lines.extend([
            f"   - GPU AMD: {gpu_devices[0].get('pci_id') or gpu_devices[0].get('device_id') or 'detectada'}",
            (
                f"   - Memória GPU: VRAM {float(memory.get('vram_used_gb') or 0.0):.2f}/"
                f"{float(memory.get('vram_total_gb') or 0.0):.2f} GB; "
                f"GTT/shared {float(memory.get('gtt_used_gb') or 0.0):.2f}/"
                f"{float(memory.get('gtt_total_gb') or 0.0):.2f} GB"
            ),
        ])

def format_console_logs(logs, state=None):
    state = state or {}
    entries = normalize_log_entries(logs)
    for entry in normalize_log_entries(state.get("log_messages", [])):
        if entry not in entries:
            entries.append(entry)

    metrics = state.get("metrics") or []
    lines = []
    step = 1
    if any("Workspace criado" in entry for entry in entries):
        lines.extend([
            f"{step}. Workspace",
            "   - Criado e inicializado.",
            "",
        ])
        step += 1

    planner_started = (
        any("Iniciando Planner Agent" in entry for entry in entries)
        or bool(state.get("plan_content"))
        or bool(metric_for_agent(metrics, "Planner Agent"))
    )
    if planner_started:
        planner_model = extract_agent_model(entries, "Planner Agent", state.get("model_planner") or "não informado")
        plan_version = state.get("plan_version") or "1.0"
        lines.extend([
            f"{step}. Planner Agent",
            "   - Acionado: sim.",
            f"   - Modelo: {planner_model}",
        ])
        if state.get("plan_content"):
            lines.append(f"   - Resultado: plano v{plan_version} salvo em implementation_plan.md.")
        else:
            lines.append("   - Resultado: plano em geração.")
        append_metric_lines(lines, metric_for_agent(metrics, "Planner Agent"))
        lines.append("")
        step += 1

    if any("Plano aprovado" in entry for entry in entries) or state.get("plan_approved"):
        lines.extend([
            f"{step}. Aprovação",
            "   - Plano aprovado para codificação.",
            "",
        ])
        step += 1

    developer_started = (
        any("Iniciando Developer Agent" in entry for entry in entries)
        or bool(state.get("files_created"))
        or metric_for_agent(metrics, "Developer Agent") is not None
        or state.get("current_step") in {"coding", "completed", "failed"} and state.get("plan_approved")
    )
    if developer_started:
        developer_model = extract_agent_model(entries, "Developer Agent", state.get("model_developer") or "não informado")
        written_files = extract_written_files(entries, state)
        lines.extend([
            f"{step}. Developer Agent",
            "   - Acionado: sim.",
            f"   - Modelo: {developer_model}",
        ])
        if written_files:
            lines.append("   - Arquivos escritos:")
            lines.extend([f"     - {filepath}" for filepath in written_files])
        elif state.get("current_step") == "coding":
            lines.append("   - Arquivos escritos: aguardando saída do agente.")
        else:
            lines.append("   - Arquivos escritos: nenhum arquivo registrado.")

        if state.get("current_step") == "completed":
            lines.append("   - Resultado: codificação concluída.")
        elif state.get("current_step") == "failed":
            lines.append("   - Resultado: falhou antes de concluir.")
        else:
            lines.append("   - Resultado: em andamento.")
        append_metric_lines(lines, metric_for_agent(metrics, "Developer Agent"))
        lines.append("")
        step += 1

    important_events = [
        entry for entry in entries
        if any(marker in entry for marker in ["Aviso:", "Erro", "Cancelado", "Timeout"])
    ]
    errors = state.get("errors") or []
    if important_events or errors:
        lines.extend([
            f"{step}. Ocorrências",
        ])
        for event in important_events:
            lines.append(f"   - {event}")
        for error in errors:
            lines.append(f"   - {error}")
        lines.append("")

    append_workflow_totals(lines, metrics, state)
    append_execution_timer_lines(lines, state)
    append_hardware_snapshot_lines(lines, state)

    clean_text = "\n".join(lines).strip()
    return clean_text if clean_text else "Nenhum evento registrado."

def render_log_pre(log_text, height=380):
    html_lines = []
    for line in log_text.splitlines():
        safe_line = html.escape(line)
        if not line.strip():
            html_lines.append('<div style="height: 8px;"></div>')
            continue

        match = re.match(r"^(\d+\.)(.*)$", line)
        if match:
            number = html.escape(match.group(1))
            rest = html.escape(match.group(2))
            html_lines.append(
                '<div style="margin: 8px 0 3px 0; color: #c9d1d9;">'
                f'<span style="color:#58a6ff; font-weight:700;">{number}</span>{rest}'
                '</div>'
            )
        elif line.startswith("   - "):
            html_lines.append(
                f'<div style="margin-left: 18px; color: #c9d1d9;">{safe_line}</div>'
            )
        elif line.startswith("     - "):
            html_lines.append(
                f'<div style="margin-left: 36px; color: #c9d1d9;">{safe_line}</div>'
            )
        else:
            html_lines.append(
                f'<div style="margin: 8px 0 3px 0; color: #c9d1d9; font-weight: 700;">{safe_line}</div>'
            )
    safe_log_text = "\n".join(html_lines)
    st.markdown(
        f'<div style="font-size: 11px; line-height: 1.55; background-color: #05070a; padding: 10px; height: {height}px; overflow-y: auto; margin: 0; border: 1px solid #21262d; border-radius: 4px; font-family: \'JetBrains Mono\', monospace;">{safe_log_text}</div>',
        unsafe_allow_html=True,
    )

def agent_loading_html(message):
    safe_message = html.escape(message)
    return f"""
    <div class="agent-loading-card">
        <span class="agent-loading-spinner"></span>
        <span class="agent-loading-dots">{safe_message}</span>
    </div>
    """

def success_completion_message(files_created):
    files = [filepath for filepath in files_created or [] if filepath]
    if files:
        files_text = "\n".join(f"- `{filepath}`" for filepath in files)
        return (
            "Desenvolvimento concluído com sucesso.\n\n"
            "Os arquivos da solução já estão disponíveis na área **Arquivos** à esquerda. "
            "Abra os arquivos gerados para revisar a implementação.\n\n"
            f"{files_text}"
        )
    return (
        "Desenvolvimento concluído com sucesso.\n\n"
        "Veja os arquivos da solução na área **Arquivos** à esquerda."
    )

def render_live_footer(project_id: str):
    active_project_js = json.dumps(project_id or "")
    active_ws_label = html.escape(project_id or "Nenhum")
    backend_url_js = json.dumps(BACKEND_URL)
    components.html(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const backendUrl = {backend_url_js};
            const activeProject = {active_project_js};
            const activeWorkspace = {json.dumps(active_ws_label)};
            const blue = "#58a6ff";
            const red = "#f85149";

            let footer = doc.getElementById("swe-footer-bar");
            if (!footer) {{
                footer = doc.createElement("div");
                footer.id = "swe-footer-bar";
                doc.body.appendChild(footer);
            }}

            footer.innerHTML = `
                <span id="swe-footer-status">Status: <strong>ONLINE</strong></span>
                <span id="swe-footer-cpu">CPU: --</span>
                <span id="swe-footer-ram">RAM: --</span>
                <span id="swe-footer-llm">LLM: --</span>
                <span id="swe-footer-temp">TEMP: --</span>
                <span id="swe-footer-timer">Timer: 0s</span>
                <span id="swe-footer-workspace">Workspace Ativo: ${{activeWorkspace}}</span>
            `;

            const style = footer.style;
            style.position = "fixed";
            style.bottom = "0";
            style.left = "0";
            style.width = "100%";
            style.height = "24px";
            style.background = "#0d1117";
            style.borderTop = "1px solid #21262d";
            style.display = "flex";
            style.justifyContent = "space-between";
            style.alignItems = "center";
            style.padding = "0 20px";
            style.fontSize = "11px";
            style.fontFamily = "'JetBrains Mono', monospace";
            style.zIndex = "999999";
            style.boxSizing = "border-box";
            style.color = blue;

            for (const item of footer.querySelectorAll("span")) {{
                item.style.color = blue;
                item.style.fontWeight = "700";
            }}

            function timerElapsedSeconds(timer) {{
                if (!timer) return 0;
                const phases = timer.phase_seconds || {{}};
                let total = Number(phases.planner || 0) + Number(phases.developer || 0);
                if (!timer.phase_seconds) total = Number(timer.accumulated_seconds || 0);
                if (timer.status === "running" && timer.segment_started_at) {{
                    total += Math.max(0, (Date.now() / 1000) - Number(timer.segment_started_at));
                }}
                return Math.max(0, total);
            }}

            function setStatus(online) {{
                const statusSpan = footer.querySelector("#swe-footer-status");
                statusSpan.style.color = online ? blue : red;
                statusSpan.innerHTML = online ? "Status: <strong>ONLINE</strong>" : "Status: <strong>OFFLINE</strong>";
            }}

            function updateMetrics() {{
                fetch(backendUrl + "/api/system/metrics")
                    .then(res => {{
                        if (!res.ok) throw new Error("Offline");
                        return res.json();
                    }})
                    .then(data => {{
                        setStatus(true);
                        footer.querySelector("#swe-footer-cpu").textContent = "CPU: " + data.cpu_percent + "%";
                        footer.querySelector("#swe-footer-ram").textContent = "RAM: " + data.ram_used_gb + " GB / " + data.ram_total_gb + " GB";
                        const ollamaProcessor = data.ollama && data.ollama.processor ? data.ollama.processor : "N/A";
                        const ollamaMemoryGb = data.ollama && data.ollama.vram_gb ? Number(data.ollama.vram_gb).toFixed(1) + " GB" : "";
                        const ollamaMemoryTarget = data.ollama && data.ollama.memory_target ? data.ollama.memory_target : "";
                        const memorySuffix = ollamaMemoryTarget.includes("shared") ? " comp." : (ollamaMemoryTarget === "system_ram" ? " RAM" : "");
                        const loadedModels = data.ollama && data.ollama.loaded_models ? " (" + data.ollama.loaded_models + ")" : "";
                        footer.querySelector("#swe-footer-llm").textContent = "LLM: " + ollamaProcessor + (ollamaMemoryGb ? " " + ollamaMemoryGb + memorySuffix : "") + loadedModels;
                        footer.querySelector("#swe-footer-temp").textContent = "TEMP: " + ((data.cpu_temp === null || data.cpu_temp === undefined) ? "N/A" : data.cpu_temp + "°C");
                    }})
                    .catch(() => {{
                        setStatus(false);
                        footer.querySelector("#swe-footer-cpu").textContent = "CPU: OFFLINE";
                        footer.querySelector("#swe-footer-ram").textContent = "RAM: OFFLINE";
                        footer.querySelector("#swe-footer-llm").textContent = "LLM: N/A";
                        footer.querySelector("#swe-footer-temp").textContent = "TEMP: N/A";
                    }});
            }}

            let cachedTimer = null;
            function updateTimerText() {{
                footer.querySelector("#swe-footer-timer").textContent = "Timer: " + Math.floor(timerElapsedSeconds(cachedTimer)) + "s";
            }}

            function updateTimerState() {{
                if (!activeProject) {{
                    cachedTimer = null;
                    updateTimerText();
                    return;
                }}
                fetch(backendUrl + "/api/project/status/" + encodeURIComponent(activeProject))
                    .then(res => {{
                        if (!res.ok) throw new Error("Timer unavailable");
                        return res.json();
                    }})
                    .then(data => {{
                        cachedTimer = data.execution_timer || null;
                        updateTimerText();
                    }})
                    .catch(() => {{
                        cachedTimer = null;
                        updateTimerText();
                    }});
            }}

            if (window.__sweFooterMetricsInterval) window.clearInterval(window.__sweFooterMetricsInterval);
            if (window.__sweFooterTimerStateInterval) window.clearInterval(window.__sweFooterTimerStateInterval);
            if (window.__sweFooterTimerTextInterval) window.clearInterval(window.__sweFooterTimerTextInterval);
            updateMetrics();
            updateTimerState();
            updateTimerText();
            window.__sweFooterMetricsInterval = window.setInterval(updateMetrics, 3000);
            window.__sweFooterTimerStateInterval = window.setInterval(updateTimerState, 1000);
            window.__sweFooterTimerTextInterval = window.setInterval(updateTimerText, 1000);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )

# ----------------- DIRECTORY SCANNER -----------------
def get_files_recursive(dir_path: Path, base_path: Path):
    items = []
    if not dir_path.exists():
        return items
    try:
        for entry in sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name in [".git", ".swe_local_agent", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules", ".idea", ".vscode"]:
                continue
            rel_path = entry.relative_to(base_path)
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "path": str(rel_path),
                    "is_dir": True,
                    "children": get_files_recursive(entry, base_path)
                })
            else:
                items.append({
                    "name": entry.name,
                    "path": str(rel_path),
                    "is_dir": False
                })
    except Exception:
        pass
    return items

def flatten_file_tree(nodes):
    flat_files = []
    for node in nodes:
        if node["is_dir"]:
            flat_files.extend(flatten_file_tree(node["children"]))
        else:
            flat_files.append(node["path"])
    return flat_files

def language_for_file(rel_path):
    suffix = rel_path.split(".")[-1].lower() if "." in rel_path else ""
    return {
        "py": "python",
        "pyw": "python",
        "md": "markdown",
        "json": "json",
        "js": "javascript",
        "ts": "typescript",
        "html": "html",
        "css": "css",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
    }.get(suffix, "text")

def load_file_into_session(project_id, project_path, rel_file):
    fetch_project_state(project_id, preserve_chat=True)
    st.session_state.selected_file = rel_file
    filepath = project_path / rel_file
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            st.session_state.file_content = f.read()
    except Exception as e:
        st.session_state.file_content = f"Error reading file: {e}"

def render_file_explorer(slot, project_id, project_path, key_suffix=""):
    with slot.container():
        with st.container(height=420):
            files_tree = get_files_recursive(project_path, project_path)

            if files_tree:
                for rel_file in flatten_file_tree(files_tree):
                    if st.button(rel_file, key=f"btn_{project_id}_{key_suffix}_{rel_file}", use_container_width=True):
                        load_file_into_session(project_id, project_path, rel_file)
                        st.rerun()
            else:
                st.info("Nenhum arquivo no workspace. Solicite uma tarefa ao agente!")

# ----------------- MAIN RENDER -----------------
backend_online = check_backend()

if not backend_online:
    st.warning("O backend do SWE Local Agent está offline. Por favor, execute o servidor FastAPI na porta 8000 para habilitar os recursos agênticos.")

# Fetch available models if empty
if backend_online and not st.session_state.available_models:
    st.session_state.available_models = fetch_available_models()

# Resolve Workspace Path
project_id = st.session_state.project_id
project_path = WORKSPACES_ROOT / project_id if project_id else None

if project_id and not st.session_state.state:
    fetch_project_state(project_id)

state = st.session_state.state
current_step = state.get("current_step", "planning") if state else "planning"
plan_version = state.get("plan_version", "1.0") if state else "1.0"
plan_content = state.get("plan_content", "") if state else ""
plan_approved = state.get("plan_approved", False) if state else False
flow_active = st.session_state.is_running or st.session_state.pending_agent_flow is not None

render_live_footer(project_id)

# Initialize columns in IDE order
col_explorer, col_editor, col_chat = st.columns([2.1, 4.4, 3.5])

# 1. LEFT COLUMN: Explorer & Workspace Settings
with col_explorer:
    col_ws_title, col_ws_ref = st.columns([0.75, 0.25])
    with col_ws_title:
        st.markdown("#### Workspace")
    with col_ws_ref:
        if st.button("🔄", key="btn_refresh_ws", help="Recarregar Workspace e Arquivos"):
            if project_id:
                fetch_project_state(project_id)
            st.rerun()
    
    # List existing workspaces
    existing_workspaces = []
    if WORKSPACES_ROOT.exists():
        existing_workspaces = [d.name for d in WORKSPACES_ROOT.iterdir() if d.is_dir()]
        
    selected_ws = st.selectbox(
        "Selecionar Projeto:",
        options=[""] + sorted(existing_workspaces),
        index=0 if not project_id or project_id not in existing_workspaces 
              else sorted(existing_workspaces).index(project_id) + 1,
        label_visibility="collapsed"
    )
    
    if selected_ws:
        if project_id != selected_ws:
            st.session_state.project_id = selected_ws
            st.session_state.selected_file = None
            st.session_state.file_content = None
            st.session_state.state = None
            fetch_project_state(selected_ws)
            st.rerun()
            
    if st.button("Novo Workspace", use_container_width=True):
        st.session_state.show_new_ws = not st.session_state.show_new_ws
        st.rerun()
        
    if st.session_state.show_new_ws:
        with st.container(border=True):
            new_project_id = st.text_input("Nome do Workspace:", key="new_project_id_input")
            if st.button("Criar Workspace", use_container_width=True):
                if new_project_id.strip():
                    try:
                        r = httpx.post(f"{BACKEND_URL}/api/project/init", json={"project_id": new_project_id.strip()})
                        if r.status_code == 200:
                            st.success(f"Workspace {new_project_id} criado!")
                            st.session_state.project_id = new_project_id.strip()
                            st.session_state.selected_file = None
                            st.session_state.file_content = None
                            st.session_state.state = None
                            st.session_state.show_new_ws = False
                            fetch_project_state(new_project_id.strip())
                            st.rerun()
                        else:
                            st.error(f"Erro ao iniciar projeto: {r.text}")
                    except Exception as e:
                        st.error(f"Falha de conexão: {e}")
                else:
                    st.warning("Insira um nome válido.")
                    
    # Model Configuration expander
    if backend_online and st.session_state.available_models:
        state = st.session_state.state
        saved_planner = state.get("model_planner") if state else None
        saved_developer = state.get("model_developer") if state else None
        
        models_list = st.session_state.available_models
        
        with st.expander("⚙️ Modelos (Ollama)", expanded=False):
            st.session_state.execution_mode = "standard"

            def_planner = choose_model(saved_planner, "llama3.2-3b-local", models_list)
            preferred_developer = "qwen2.5-coder-3b-developer"
            def_dev = choose_model(saved_developer, preferred_developer, models_list)
            
            idx_planner = models_list.index(def_planner) if def_planner in models_list else 0
            idx_dev = models_list.index(def_dev) if def_dev in models_list else 0
            
            selected_planner = st.selectbox("Planner Agent (Plano/Raciocínio):", options=models_list, index=idx_planner, key="sb_planner")
            selected_developer = st.selectbox("Developer Agent (Código/Escrita):", options=models_list, index=idx_dev, key="sb_developer")
            if st.button("Preparar modelos", key="btn_prepare_models", use_container_width=True):
                with st.spinner("Solicitando pré-aquecimento..."):
                    request_fast_start_models(selected_planner, selected_developer)
                st.toast("Pré-aquecimento dos modelos iniciado em segundo plano!", icon="🔥")
                
    st.markdown('<hr style="margin: 10px 0; border-color: #21262d;"/>', unsafe_allow_html=True)
    
    if project_id and project_path:
        st.markdown("##### Arquivos")
        file_explorer_slot = st.empty()
        render_file_explorer(file_explorer_slot, project_id, project_path, key_suffix="initial")
    else:
        file_explorer_slot = None
        st.info("Nenhum workspace aberto.")

# 2. MIDDLE COLUMN: Code Editor / Central Workspace
with col_editor:
    st.markdown("#### Visualizador")
    
    if project_id and project_path:
        if st.session_state.selected_file:
            rel_path = st.session_state.selected_file
            st.markdown(f"""
            <div style="background-color: #0d1117; padding: 6px 12px; border: 1px solid #21262d; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; font-size: 12px; color: #c9d1d9; font-family: 'JetBrains Mono', monospace;">
                {project_id} / {rel_path}
            </div>
            """, unsafe_allow_html=True)
            
            tab_view, tab_logs = st.tabs(["Visualizador", "Logs de Execução"])
            
            with tab_view:
                lang = language_for_file(rel_path)
                with st.container(height=420):
                    st.code(st.session_state.file_content, language=lang)
                    
            with tab_logs:
                with st.container(height=420):
                    log_text = format_console_logs(st.session_state.console_logs, st.session_state.state)
                    render_log_pre(log_text)
                    
        else:
            if current_step == "planning" and plan_content and not plan_approved:
                tab_welcome, tab_logs = st.tabs(["📋 Aprovar Plano", "Logs de Execução"])
                
                with tab_welcome:
                    with st.container(height=420):
                        st.markdown("""
                        <div style="background-color: #2b1f1d; border: 1px solid #ff7b72; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                            <h4 style="margin: 0; color: #ff7b72;">Aprovação de Plano Pendente</h4>
                            <p style="margin: 5px 0 0 0; font-size: 12px; color: #c9d1d9;">O Planner Agent concluiu o plano e salvou o arquivo <code>implementation_plan.md</code>. Abra esse arquivo no painel Arquivos à esquerda, revise as decisões e então aprove a codificação ou envie feedback para gerar uma nova versão.</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.info("Revise `implementation_plan.md` pelo explorador de arquivos. O chat mostra apenas o status para manter a conversa limpa.")
                        
                        # Feedback input in main column
                        feedback_main = st.text_area("Enviar feedback (Opcional):", placeholder="Ajustes no plano...", height=68, key="feedback_textarea_main")
                        
                        if flow_active:
                            st.info("Execução em andamento. Os controles de aprovação voltam quando o fluxo terminar.")
                        else:
                            col_approve_main, col_feedback_main = st.columns([1, 1])
                            with col_approve_main:
                                if st.button("Aprovar e Codificar", key="btn_approve_main", use_container_width=True):
                                    payload = {
                                        "project_id": project_id,
                                        "model_planner": st.session_state.get("sb_planner"),
                                        "model_developer": st.session_state.get("sb_developer"),
                                        "execution_mode": "standard"
                                    }
                                    queue_approval_flow(payload)
                                    
                            with col_feedback_main:
                                if st.button("Ajustar Plano", key="btn_feedback_main", use_container_width=True):
                                    if feedback_main.strip():
                                        st.session_state.chat_history.append({
                                            "role": "user",
                                            "content": f"Ajustar plano com feedback: {feedback_main}"
                                        })
                                        payload = {
                                            "project_id": project_id,
                                            "prompt": "",
                                            "feedback": feedback_main,
                                            "model_planner": st.session_state.get("sb_planner"),
                                            "model_developer": st.session_state.get("sb_developer"),
                                        "execution_mode": "standard"
                                        }
                                        queue_agent_flow(payload, "/api/project/prompt")
            else:
                tab_welcome, tab_logs = st.tabs(["Bem-vindo", "Logs de Execução"])
                
                with tab_welcome:
                    with st.container(height=420):
                        st.markdown(f"""
                        <div class="welcome-card" style="margin-top: 0; border-radius: 4px;">
                            <h3 style="margin-top: 0; color: #58a6ff;">Workspace: {project_id}</h3>
                            <p style="font-size: 13px; line-height: 1.6;">Use o painel de chat à direita para solicitar planos de arquitetura, refatorações, criação de funcionalidades ou correções de bugs offline.</p>
                            <div style="margin-top:20px; font-size:12px; color:#8b949e; border-top: 1px solid #21262d; padding-top: 15px;">
                                Dica: Clique em qualquer arquivo no explorador lateral esquerdo para abri-lo aqui no visualizador.
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            
            with tab_logs:
                with st.container(height=420):
                    log_text = format_console_logs(st.session_state.console_logs, st.session_state.state)
                    render_log_pre(log_text)
                    
    else:
        with st.container(height=450):
            st.markdown("""
            <div class="welcome-card" style="margin-top: 20px; text-align: center; border-radius: 4px;">
                <h2 style="color: #58a6ff; margin-bottom: 15px;">SWE Local Agent IDE</h2>
                <p style="font-size: 14px; line-height: 1.6; color: #c9d1d9;">Esta é uma IDE agêntica de desenvolvimento de software 100% offline projetada para o seu hardware local.</p>
                <div style="margin-top: 30px; padding: 15px; background-color: #161b22; border-radius: 4px; border: 1px solid #21262d;">
                    <p style="color: #8b949e; font-size: 13px; margin: 0;">
                        Dica: Selecione um projeto existente ou crie um novo workspace na barra de Workspace no canto esquerdo.
                    </p>
                </div>
            </div>
            """, unsafe_allow_html=True)
 
# 3. RIGHT COLUMN: Chat Dialog with Agents
with col_chat:
    st.markdown("#### Agent Chat")
    
    if project_id and project_path:
        
        # Dynamically calculate container height if plan approval is pending
        is_approval_pending = (current_step == "planning" and plan_content and not plan_approved)
        container_height = 360 if is_approval_pending else 520
        chat_container = st.container(border=True, height=container_height)
        
        with chat_container:
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    safe_user_text = html.escape(msg.get("content", "")).replace("\n", "<br/>")
                    st.markdown(f"""
                    <div class="user-chat-card">
                        <div class="user-chat-label">Você</div>
                        <div>{safe_user_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    continue

                with st.chat_message(msg["role"]):
                    if "agent" in msg and msg["agent"]:
                        st.markdown(f"**[{msg['agent']}]**")
                    if "thinking" in msg and msg["thinking"]:
                        safe_thinking = html.escape(msg["thinking"]).replace("\n", "<br/>")
                        st.markdown(f"""
                        <details style="background-color: #161b22; padding: 6px; border-radius: 4px; border: 1px solid #21262d; font-size: 11px; margin-bottom: 8px;">
                            <summary style="cursor: pointer; color: #8b949e; font-weight: bold;">[Raciocínio]</summary>
                            <div style="margin-top: 5px; color: #c9d1d9; white-space: pre-wrap;">{safe_thinking}</div>
                        </details>
                        """, unsafe_allow_html=True)
                    st.markdown(msg["content"])

            if st.session_state.pending_agent_flow and not st.session_state.is_running:
                pending_endpoint = st.session_state.pending_agent_flow.get("endpoint")
                if pending_endpoint == "/api/project/prompt":
                    pending_message = "Preparando Planner Agent e coletando contexto do workspace"
                else:
                    pending_message = "Preparando Developer Agent"
                st.markdown(agent_loading_html(pending_message), unsafe_allow_html=True)
                    
        # SSE Execution Loop
        def execute_agent_flow(payload, endpoint):
            st.session_state.is_running = True
            current_agent = "Planner Agent" if endpoint == "/api/project/prompt" else "Developer Agent"

            def render_agent_loading(placeholder, message):
                placeholder.markdown(agent_loading_html(message), unsafe_allow_html=True)

            def render_agent_status(placeholder, message):
                safe_message = html.escape(message)
                placeholder.markdown(f"""
                <div style="background-color: #0d1117; border-left: 3px solid #58a6ff; padding: 8px 10px; border-radius: 4px; font-size: 11px; color: #c9d1d9; line-height: 1.55;">
                    {safe_message}
                </div>
                """, unsafe_allow_html=True)

            with chat_container:
                with st.chat_message("assistant"):
                    st.markdown(f"**[{current_agent}]**")
                    thinking_placeholder = st.empty()
                    response_placeholder = st.empty()
                    if endpoint == "/api/project/prompt":
                        render_agent_loading(response_placeholder, "Preparando Planner Agent e coletando contexto do workspace")
                    else:
                        render_agent_loading(response_placeholder, "Preparando Developer Agent")
                    
            thinking_text = ""
            response_text = ""
            
            def hide_planner_code_lines(lines):
                code_pattern = re.compile(
                    r"^\s*(?:import\s+\w+|from\s+\w+\s+import\s+|def\s+\w+\(|class\s+\w+|"
                    r"print\s*\(|return\b|if\s+.+:|elif\s+.+:|else:|for\s+.+:|while\s+.+:|"
                    r"try:|except\b.*:|with\s+.+:|self\.|[A-Za-z_][\w\.]*\s*=|"
                    r"[A-Za-z_][\w\.]*\([^)]*\))",
                    flags=re.IGNORECASE,
                )
                cleaned = []
                omitted = False
                for line in lines:
                    if code_pattern.search(line) or "time.sleep(" in line or "time.time(" in line:
                        omitted = True
                        continue
                    cleaned.append(line)
                if omitted:
                    cleaned.append("[trecho de código ocultado: Planner apenas descreve o plano]")
                return cleaned

            def render_live_preview(text, placeholder, is_planner=False):
                """Show live rolling preview of the last 3 lines of agent output."""
                lines = [line for line in text.strip().splitlines() if line.strip()]
                if is_planner:
                    lines = hide_planner_code_lines(lines)
                preview_lines = lines[-3:] if len(lines) > 3 else lines
                preview = "\n".join(preview_lines)
                safe_preview = html.escape(preview).replace("\n", "<br/>")
                char_count = len(text.strip())
                action_label = "Gerando plano" if is_planner else "Gerando solução"
                placeholder.markdown(f"""
                <div style="font-size: 11px; color: #8b949e; margin-bottom: 4px;">
                    {action_label}... ({char_count} chars)
                </div>
                <div style="background-color: #0d1117; border-left: 3px solid #58a6ff; padding: 8px 10px; border-radius: 4px; font-size: 11px; color: #c9d1d9; line-height: 1.55; font-family: 'JetBrains Mono', monospace;">
                    {safe_preview}
                </div>
                """, unsafe_allow_html=True)
            
            try:
                import httpx_sse
                with httpx.Client(timeout=600.0) as client:
                    with httpx_sse.connect_sse(client, "POST", f"{BACKEND_URL}{endpoint}", json=payload) as event_source:
                        for sse in event_source.iter_sse():
                            data = json.loads(sse.data)
                            event = data.get("event")
                            
                            if event == "token":
                                token_type = data.get("type")
                                token_data = data.get("data")
                                if token_type == "thinking":
                                    thinking_text += token_data
                                    # Show last 3 lines of reasoning, auto-scrolling
                                    lines = [l for l in thinking_text.strip().splitlines() if l.strip()]
                                    preview_lines = lines[-3:] if len(lines) > 3 else lines
                                    safe_preview = html.escape("\n".join(preview_lines)).replace("\n", "<br/>")
                                    thinking_placeholder.markdown(f"""
                                    <div class="reasoning-box">
                                        <strong>[Raciocínio Interno]:</strong><br/>
                                        {safe_preview}
                                    </div>
                                    """, unsafe_allow_html=True)
                                elif token_type == "response":
                                    response_text += token_data
                                    is_planner = (endpoint == "/api/project/prompt")
                                    render_live_preview(response_text, response_placeholder, is_planner=is_planner)
                                    
                            elif event == "status":
                                status_msg = data.get("data") or ""
                                st.toast(status_msg)
                                st.session_state.console_logs.append(status_msg)
                                if not response_text.strip():
                                    render_agent_status(response_placeholder, status_msg)
                                
                                if "Iniciando " in status_msg:
                                    if response_text.strip() or thinking_text.strip():
                                        st.session_state.chat_history.append({
                                            "role": "assistant",
                                            "thinking": thinking_text if thinking_text else None,
                                            "content": response_text,
                                            "agent": current_agent
                                        })
                                    
                                    if "Avaliação Inicial" in status_msg:
                                        next_agent = "Project Manager (Estratégia)"
                                    elif "Planner" in status_msg:
                                        next_agent = "Planner Agent"
                                    elif "Developer" in status_msg:
                                        next_agent = "Developer Agent"
                                    elif "Avaliação Final" in status_msg:
                                        next_agent = "Project Manager (Validação)"
                                    else:
                                        next_agent = "Agent"

                                    if not response_text.strip() and not thinking_text.strip() and next_agent == current_agent:
                                        render_agent_status(response_placeholder, status_msg)
                                        continue

                                    current_agent = next_agent
                                    
                                    thinking_text = ""
                                    response_text = ""
                                    with chat_container:
                                        with st.chat_message("assistant"):
                                            st.markdown(f"**[{current_agent}]**")
                                            thinking_placeholder = st.empty()
                                            response_placeholder = st.empty()
                                            render_agent_status(response_placeholder, status_msg)
                            
                            elif event == "files_changed":
                                changed_files = data.get("files") or []
                                latest_file = data.get("latest")
                                if st.session_state.state is not None:
                                    existing_files = st.session_state.state.get("files_created", []) or []
                                    merged_files = list(existing_files)
                                    for changed_file in changed_files:
                                        if changed_file not in merged_files:
                                            merged_files.append(changed_file)
                                    st.session_state.state["files_created"] = merged_files
                                if latest_file:
                                    st.session_state.console_logs.append(f"Escrito: {latest_file}")
                                else:
                                    st.session_state.console_logs.append("Arquivos atualizados no workspace.")
                                if file_explorer_slot is not None and project_path:
                                    st.session_state.file_explorer_render_nonce += 1
                                    file_explorer_slot.empty()
                                    render_file_explorer(
                                        file_explorer_slot,
                                        project_id,
                                        project_path,
                                        key_suffix=f"live_{st.session_state.file_explorer_render_nonce}",
                                    )
                                
                            elif event == "node_complete":
                                current_logs = list(st.session_state.console_logs)
                                st.session_state.state = data.get("state")
                                merged_logs = []
                                for log_item in current_logs + st.session_state.state.get("log_messages", []):
                                    if log_item not in merged_logs:
                                        merged_logs.append(log_item)
                                st.session_state.console_logs = merged_logs
                                if endpoint == "/api/project/prompt":
                                    final_res = plan_ready_message(st.session_state.state.get("plan_version", "1.0"))
                                else:
                                    errors = st.session_state.state.get("errors") or []
                                    if st.session_state.state.get("current_step") == "failed":
                                        error_lines = "\n".join(f"- {error}" for error in errors) if errors else "- Developer Agent não conseguiu concluir a entrega."
                                        final_res = (
                                            "Fluxo encerrado antes da conclusão.\n\n"
                                            f"{error_lines}\n\n"
                                            "Veja os detalhes no log de execução."
                                        )
                                    else:
                                        final_res = success_completion_message(
                                            st.session_state.state.get("files_created", [])
                                        )
                                
                                st.session_state.chat_history.append({
                                    "role": "assistant",
                                    "thinking": thinking_text if thinking_text else None,
                                    "content": final_res,
                                    "agent": current_agent
                                })
                                break
                                
                            elif event == "error":
                                err_msg = data.get("data")
                                st.error(f"Erro no processamento: {err_msg}")
                                st.session_state.chat_history.append({
                                    "role": "assistant",
                                    "content": f"Desculpe, ocorreu um erro durante a execução: {err_msg}",
                                    "agent": current_agent
                                })
                                break
            except Exception as e:
                st.error(f"Erro de comunicação com o backend: {e}")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Desculpe, ocorreu um erro de comunicação com o backend: {e}",
                    "agent": current_agent
                })
            
            # Always refresh state from backend before rerun to ensure
            # files and logs are synchronized, regardless of SSE reliability
            try:
                fetch_project_state(project_id, preserve_chat=True)
            except Exception:
                pass
                
            st.session_state.is_running = False
            st.rerun()

        # Stop Button while any agent workflow is active or about to start.
        if flow_active:
            if st.button("🛑 Interromper Execução", type="secondary", use_container_width=True):
                stop_agent_execution(project_id)
                st.rerun()

        # Approval Block or Standard Input Block
        if flow_active:
            st.info("Execução em andamento. Acompanhe as mensagens dos agentes acima.")
        elif current_step == "planning" and plan_content and not plan_approved:
            # Custom styled, highly readable amber warning card inside details box
            st.markdown("""
            <div style="background-color: #3b2314; border: 1px solid #d29922; color: #ffdfa5; padding: 10px 14px; border-radius: 6px; font-size: 13px; font-weight: bold; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                ⚠️ Plano concluído. Revise <code>implementation_plan.md</code> no painel Arquivos e então aprove a codificação ou envie um feedback de ajuste.
            </div>
            """, unsafe_allow_html=True)
                
            feedback_text = st.text_area("Enviar feedback (Opcional):", placeholder="Ajustes no plano...", height=92, key="feedback_textarea")
            
            col_approve, col_feedback = st.columns([1, 1])
            
            with col_approve:
                if st.button("Aprovar e Codificar", use_container_width=True):
                    payload = {
                        "project_id": project_id,
                        "model_planner": st.session_state.get("sb_planner"),
                        "model_developer": st.session_state.get("sb_developer"),
                        "execution_mode": "standard"
                    }
                    queue_approval_flow(payload)
                    
            with col_feedback:
                if st.button("Ajustar Plano", use_container_width=True):
                    if feedback_text.strip():
                        st.session_state.chat_history.append({
                            "role": "user",
                            "content": f"Ajustar plano com feedback: {feedback_text}"
                        })
                        payload = {
                            "project_id": project_id,
                            "prompt": "",
                            "feedback": feedback_text,
                            "model_planner": st.session_state.get("sb_planner"),
                            "model_developer": st.session_state.get("sb_developer"),
                            "execution_mode": "standard"
                        }
                        queue_agent_flow(payload, "/api/project/prompt")
                    else:
                        st.warning("Escreva o feedback antes de ajustar.")
        else:
            prompt = st.chat_input("Digite sua solicitação de software...", disabled=flow_active)
            if prompt:
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": prompt
                })
                payload = {
                    "project_id": project_id,
                    "prompt": prompt,
                    "model_planner": st.session_state.get("sb_planner"),
                    "model_developer": st.session_state.get("sb_developer"),
                    "execution_mode": "standard"
                }
                queue_agent_flow(payload, "/api/project/prompt")

        pending_flow = st.session_state.pending_agent_flow
        if pending_flow and not st.session_state.is_running:
            st.session_state.pending_agent_flow = None
            execute_agent_flow(pending_flow["payload"], pending_flow["endpoint"])
    else:
        st.info("Selecione ou crie um workspace na esquerda para iniciar o chat com os agentes.")
