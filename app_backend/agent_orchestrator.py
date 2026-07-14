import re
import os
import json
import logging
import asyncio
import time
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from langchain_core.runnables import RunnableConfig
import httpx

from app_backend.ollama_client import OllamaClient
from app_backend.security import SecuritySandbox
from app_backend.git_manager import GitManager

logger = logging.getLogger(__name__)

async def get_available_models() -> List[str]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []

def resolve_model(model_name: Optional[str], available_models: List[str]) -> str:
    if not model_name:
        return ""
    if model_name in available_models:
        return model_name
    if f"{model_name}:latest" in available_models:
        return f"{model_name}:latest"
    # Substring matching (case insensitive)
    for m in available_models:
        if model_name.lower() in m.lower():
            return m
    requested_tokens = _model_match_tokens(model_name)
    for m in available_models:
        if requested_tokens and requested_tokens.issubset(_model_match_tokens(m)):
            return m
    return model_name

def _model_match_tokens(model_name: str) -> set[str]:
    ignored_tokens = {"latest", "local"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", model_name.lower())
        if token not in ignored_tokens
    }


class AgentState(TypedDict):
    project_id: str
    prompt: str
    plan_version: str
    plan_content: str
    user_feedback: Optional[str]
    plan_approved: bool
    current_step: str  # "planning", "coding", "completed", "failed"
    errors: List[str]
    files_created: List[str]
    self_healing_attempts: int
    log_messages: List[str]
    model_planner: Optional[str]
    model_developer: Optional[str]
    execution_mode: Optional[str]
    execution_timer: Optional[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    runtime: Optional[Dict[str, Any]]
    hardware_snapshots: List[Dict[str, Any]]
    quality_checks: Dict[str, Any]


INTERNAL_CONTEXT_FILES = {"implementation_plan.md"}
GENERATED_FILE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".md",
}
DEFAULT_PLANNER_MODEL = "llama3.2-3b-local"
DEFAULT_DEVELOPER_MODEL = "qwen2.5-coder-3b-local"
PLANNER_WORKSPACE_CONTEXT_MAX_CHARS = 4000
DEVELOPER_WORKSPACE_CONTEXT_MAX_CHARS = 12000
PLANNER_RUNTIME_OPTIONS = {
    "num_ctx": 2048,
    "temperature": 0.3,
    "num_predict": 384,
}
DEVELOPER_RUNTIME_OPTIONS = {
    "num_ctx": 4096,
    "temperature": 0.1,
    "num_predict": 1000,
}
EXECUTION_MODE_STANDARD = "standard"
TIMER_STATUS_RUNNING = "running"
TIMER_STATUS_PAUSED = "paused"
TIMER_STATUS_COMPLETED = "completed"
QUALITY_STOPWORDS = {
    "app", "aplicativo", "aplicacao", "desenvolva", "desenvolver", "simples",
    "minimamente", "modular", "modularidade", "python", "linguagem",
    "programacao", "programação", "controle", "usar", "como", "para",
    "deve", "ser", "com", "sem", "uma", "um", "dos", "das", "por",
    "que", "este", "esta", "esse", "essa", "principal",
}
SUSPICIOUS_DOMAIN_SHIFTS = {
    "pomodoro": {"pomodoro"},
    "cronometro": {"cronometro", "cronômetro"},
    "timer": {"timer"},
    "temporizador": {"temporizador"},
}

def parse_files_from_output(output_text: str) -> List[Tuple[str, str]]:
    """
    Parses Qwen-Coder's text output and extracts file writes formatted as:
    [FILE: filepath]
    ```language
    code
    ```
    """
    cleaned_output = output_text.replace("\r\n", "\n")
    extracted: List[Tuple[str, str]] = []
    seen_paths = set()

    valid_extension_pattern = "|".join(re.escape(ext.lstrip(".")) for ext in sorted(GENERATED_FILE_EXTENSIONS))

    file_marker_pattern = re.compile(
        r"^\s*(?:"
        r"\[(?:FILE|ARQUIVO)\s*:?\s*([^\]\n]+)\]"
        r"|(?:FILE|ARQUIVO)\s*:\s*([^\n]+?)"
        r")\s*$\s*```[^\n`]*\n(.*?)\n\s*```",
        flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )

    heading_pattern = re.compile(
        rf"^\s{{0,3}}#{{2,5}}\s+(?:arquivo\s+)?`?([^`\n]+?\.({valid_extension_pattern}))`?\s*$"
        r"\s*```[^\n`]*\n(.*?)\n\s*```",
        flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )

    fenced_filename_pattern = re.compile(
        rf"^\s*```[^\n`]*\n\s*([A-Za-z0-9_./-]+\.({valid_extension_pattern}))\s*\n\s*```\s*"
        r"```[^\n`]*\n(.*?)\n\s*```",
        flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )

    commented_filename_pattern = re.compile(
        rf"```[^\n`]*\n\s*#\s*([A-Za-z0-9_./-]+\.({valid_extension_pattern}))\s*\n(.*?)\n\s*```",
        flags=re.DOTALL | re.IGNORECASE,
    )

    def add_file(raw_path: str, code: str) -> None:
        path = raw_path.strip().strip("`'\"")
        path = re.sub(r"^\s*(?:path|caminho)\s*:\s*", "", path, flags=re.IGNORECASE).strip()
        if Path(path).suffix.lower() not in GENERATED_FILE_EXTENSIONS:
            return
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        extracted.append((path, code.strip()))

    for match in file_marker_pattern.finditer(cleaned_output):
        add_file(match.group(1) or match.group(2) or "", match.group(3))

    for match in heading_pattern.finditer(cleaned_output):
        add_file(match.group(1), match.group(3))

    for match in fenced_filename_pattern.finditer(cleaned_output):
        add_file(match.group(1), match.group(3))

    for match in commented_filename_pattern.finditer(cleaned_output):
        add_file(match.group(1), match.group(3))

    return extracted

def save_agent_debug_output(project_dir: Path, filename: str, content: str) -> str:
    state_dir = project_dir / ".swe_local_agent"
    state_dir.mkdir(exist_ok=True)
    debug_path = state_dir / filename
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(content)
    return debug_path.relative_to(project_dir).as_posix()

def normalize_execution_mode(mode: Optional[str]) -> str:
    return EXECUTION_MODE_STANDARD

def _timer_phase_seconds(timer: Optional[Dict[str, Any]]) -> Dict[str, float]:
    phases = (timer or {}).get("phase_seconds") or {}
    if not phases and timer and timer.get("accumulated_seconds"):
        return {
            "planner": float(timer.get("accumulated_seconds") or 0.0),
            "developer": 0.0,
        }
    return {
        "planner": float(phases.get("planner") or 0.0),
        "developer": float(phases.get("developer") or 0.0),
    }

def execution_timer_phase_elapsed(timer: Optional[Dict[str, Any]], phase: str, now: Optional[float] = None) -> float:
    if not timer:
        return 0.0

    current_time = time.time() if now is None else now
    phase_totals = _timer_phase_seconds(timer)
    accumulated = phase_totals.get(phase, 0.0)
    started_at = timer.get("segment_started_at")
    if timer.get("status") == TIMER_STATUS_RUNNING and timer.get("current_phase") == phase and started_at:
        return max(0.0, accumulated + (current_time - float(started_at)))
    return max(0.0, accumulated)

def execution_timer_elapsed(timer: Optional[Dict[str, Any]], now: Optional[float] = None) -> float:
    if not timer:
        return 0.0
    return (
        execution_timer_phase_elapsed(timer, "planner", now)
        + execution_timer_phase_elapsed(timer, "developer", now)
    )

def start_execution_timer(
    state: Dict[str, Any],
    reset: bool = False,
    now: Optional[float] = None,
    phase: str = "planner",
) -> Dict[str, Any]:
    current_time = time.time() if now is None else now
    previous_timer = state.get("execution_timer")
    phase_totals = {"planner": 0.0, "developer": 0.0} if reset else _timer_phase_seconds(previous_timer)
    timer_data = {
        "status": TIMER_STATUS_RUNNING,
        "current_phase": phase,
        "phase_seconds": phase_totals,
        "accumulated_seconds": sum(phase_totals.values()),
        "segment_started_at": current_time,
    }
    state["execution_timer"] = timer_data
    return timer_data

def _accumulate_current_phase(timer: Optional[Dict[str, Any]], now: float) -> Dict[str, float]:
    phase_totals = _timer_phase_seconds(timer)
    if timer and timer.get("status") == TIMER_STATUS_RUNNING:
        phase = timer.get("current_phase")
        started_at = timer.get("segment_started_at")
        if phase in phase_totals and started_at:
            phase_totals[phase] = max(0.0, phase_totals[phase] + (now - float(started_at)))
    return phase_totals

def pause_execution_timer(state: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    current_time = time.time() if now is None else now
    phase_totals = _accumulate_current_phase(state.get("execution_timer"), current_time)
    timer_data = {
        "status": TIMER_STATUS_PAUSED,
        "current_phase": None,
        "phase_seconds": phase_totals,
        "accumulated_seconds": sum(phase_totals.values()),
        "segment_started_at": None,
    }
    state["execution_timer"] = timer_data
    return timer_data

def complete_execution_timer(state: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    current_time = time.time() if now is None else now
    phase_totals = _accumulate_current_phase(state.get("execution_timer"), current_time)
    timer_data = {
        "status": TIMER_STATUS_COMPLETED,
        "current_phase": None,
        "phase_seconds": phase_totals,
        "accumulated_seconds": sum(phase_totals.values()),
        "segment_started_at": None,
    }
    state["execution_timer"] = timer_data
    return timer_data

def format_execution_timer_seconds(timer: Optional[Dict[str, Any]]) -> str:
    return f"{execution_timer_elapsed(timer):.2f}s"

def strip_metrics_footer(text: str) -> str:
    return re.sub(r"\n\n---\n\*.*?Tempo:.*?TPS\*\s*$", "", text.strip(), flags=re.DOTALL)

def looks_like_implementation_plan(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "plano",
        "estrutura",
        "arquivo",
        "rota",
        "endpoint",
        "teste",
        "implement",
    ]
    return bool(text.strip()) and sum(marker in lowered for marker in markers) >= 2

def sanitize_planner_output(plan_content: str) -> Tuple[str, int]:
    """
    Keeps the Planner in planning mode by removing implementation code blocks.
    The Developer Agent is the only node allowed to generate source files.
    """
    content = plan_content.strip()
    outer_markdown = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*?)\n```", content, flags=re.DOTALL | re.IGNORECASE)
    if outer_markdown:
        content = outer_markdown.group(1).strip()

    removed_blocks = 0

    def replace_fence(match: re.Match) -> str:
        nonlocal removed_blocks
        removed_blocks += 1
        return (
            "\n> Bloco de código omitido pelo orquestrador: "
            "o Planner deve descrever a implementação, não escrever os arquivos finais.\n"
        )

    content = re.sub(r"```[a-zA-Z0-9_-]*\s*\n.*?\n```", replace_fence, content, flags=re.DOTALL)

    code_line_pattern = re.compile(
        r"^\s*(?:"
        r"import\s+\w+|from\s+\w+\s+import\s+|def\s+\w+\(|class\s+\w+|"
        r"print\s*\(|return\b|if\s+.+:|elif\s+.+:|else:|for\s+.+:|while\s+.+:|"
        r"try:|except\b.*:|with\s+.+:|self\.|[A-Za-z_][\w\.]*\s*=|"
        r"[A-Za-z_][\w\.]*\([^)]*\)"
        r")",
        flags=re.IGNORECASE,
    )
    sanitized_lines = []
    removed_inline_code = False
    previous_was_omission = False
    for line in content.splitlines():
        if code_line_pattern.search(line) or "time.sleep(" in line or "time.time(" in line:
            removed_inline_code = True
            if not previous_was_omission:
                sanitized_lines.append(
                    "> Linha de codigo omitida pelo orquestrador: "
                    "o Planner deve descrever comportamento, nao implementar."
                )
                previous_was_omission = True
            continue
        sanitized_lines.append(line)
        previous_was_omission = False

    if removed_inline_code:
        removed_blocks += 1
        content = "\n".join(sanitized_lines)
    return content.strip(), removed_blocks

def normalize_text_for_quality(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_text.lower()

def extract_scope_keywords(prompt: str) -> List[str]:
    normalized = normalize_text_for_quality(prompt)
    tokens = re.findall(r"[a-z0-9]{4,}", normalized)
    keywords = []
    for token in tokens:
        if token in QUALITY_STOPWORDS:
            continue
        if token not in keywords:
            keywords.append(token)
    return keywords[:8]

def extract_planned_files(plan_content: str) -> List[str]:
    valid_extensions = "|".join(re.escape(ext.lstrip(".")) for ext in sorted(GENERATED_FILE_EXTENSIONS))
    files = []
    for match in re.finditer(
        rf"\b([A-Za-z0-9_./-]+\.({valid_extensions}))\b",
        plan_content or "",
        flags=re.IGNORECASE,
    ):
        path = match.group(1).strip("`'\"")
        if path not in files:
            files.append(path)
    return files

def detect_domain_shift(prompt: str, text: str) -> List[str]:
    normalized_prompt = normalize_text_for_quality(prompt)
    normalized_lines = normalize_text_for_quality(text).splitlines()
    negation_markers = ("nao ", "sem ", "evite", "fora de escopo", "nao implementar", "nao entregue")
    shifts = []
    for label, variants in SUSPICIOUS_DOMAIN_SHIFTS.items():
        prompt_mentions = any(normalize_text_for_quality(variant) in normalized_prompt for variant in variants)
        text_mentions = False
        for variant in variants:
            normalized_variant = normalize_text_for_quality(variant)
            for line in normalized_lines:
                if normalized_variant in line and not any(marker in line for marker in negation_markers):
                    text_mentions = True
                    break
            if text_mentions:
                break
        if text_mentions and not prompt_mentions:
            shifts.append(label)
    return shifts

def build_quality_checks(
    prompt: str,
    plan_content: str,
    *,
    removed_code_blocks: int = 0,
    files_created: Optional[List[str]] = None,
    developer_output: str = "",
    stage: str = "planner",
) -> Dict[str, Any]:
    normalized_plan = normalize_text_for_quality(plan_content)
    combined_output = f"{plan_content}\n{developer_output}"
    scope_keywords = extract_scope_keywords(prompt)
    missing_keywords = [
        keyword for keyword in scope_keywords
        if keyword not in normalize_text_for_quality(combined_output)
    ]
    found_keywords = [keyword for keyword in scope_keywords if keyword not in missing_keywords]

    has_scope_summary = "escopo entendido" in normalized_plan
    has_minimum_features = "funcionalidades minimas" in normalized_plan or "funcionalidades obrigatorias" in normalized_plan
    has_acceptance_criteria = "criterios de aceite" in normalized_plan or "criterio de aceite" in normalized_plan
    has_out_of_scope = "fora de escopo" in normalized_plan
    planned_files = extract_planned_files(plan_content)
    files_created = list(files_created or [])
    missing_planned_files = [
        filepath for filepath in planned_files
        if filepath not in files_created
    ] if stage == "developer" else []
    domain_shift_terms = detect_domain_shift(prompt, combined_output)

    warnings = []
    blocking_issues = []

    if not has_scope_summary:
        warnings.append("Plano sem seção 'Escopo entendido'.")
    if not has_minimum_features:
        warnings.append("Plano sem funcionalidades mínimas obrigatórias.")
    if not has_out_of_scope:
        warnings.append("Plano sem seção 'Fora de escopo'.")
    if not has_acceptance_criteria:
        blocking_issues.append("Plano sem critérios de aceite explícitos.")
    if missing_keywords and len(missing_keywords) == len(scope_keywords) and scope_keywords:
        warnings.append("Plano não preserva palavras centrais do pedido original.")
    if domain_shift_terms:
        blocking_issues.append(
            "Possível desvio de domínio: "
            + ", ".join(domain_shift_terms)
            + " aparece no plano/entrega, mas não no pedido original."
        )
    if removed_code_blocks:
        warnings.append(
            f"Planner gerou {removed_code_blocks} bloco(s)/linha(s) de código; o conteúdo foi sanitizado."
        )
    if len(planned_files) > 3:
        warnings.append("Plano lista mais de 3 arquivos para uma tarefa simples.")
    if stage == "developer" and missing_planned_files:
        warnings.append("Developer não gerou todos os arquivos planejados.")
    if stage == "developer" and len(files_created) <= 2 and "modular" in normalize_text_for_quality(prompt):
        warnings.append("Entrega modular com poucos arquivos; revisar se o escopo foi simplificado demais.")

    status = "blocked" if blocking_issues else ("warning" if warnings else "passed")
    return {
        "stage": stage,
        "status": status,
        "blocking": bool(blocking_issues),
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "has_scope_summary": has_scope_summary,
        "has_minimum_features": has_minimum_features,
        "has_acceptance_criteria": has_acceptance_criteria,
        "has_out_of_scope": has_out_of_scope,
        "scope_keywords": scope_keywords,
        "scope_keywords_found": found_keywords,
        "missing_scope_keywords": missing_keywords,
        "suspicious_domain_shift": bool(domain_shift_terms),
        "domain_shift_terms": domain_shift_terms,
        "planner_code_removed_blocks": removed_code_blocks,
        "planned_files": planned_files,
        "files_created": files_created,
        "files_match_plan": not missing_planned_files,
        "missing_planned_files": missing_planned_files,
    }

def write_state_snapshot(project_dir: Path, state: AgentState, updates: Dict[str, Any]) -> None:
    state_dir = project_dir / ".swe_local_agent"
    state_dir.mkdir(exist_ok=True)
    state_data = dict(state)
    state_data.update(updates)
    with open(state_dir / "state.json", "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)

def collect_workspace_context(project_dir: Path, files_created: List[str], max_chars: int = 60000) -> str:
    context_parts = []
    seen_paths = set()
    candidate_paths = files_created or [
        path.relative_to(project_dir).as_posix()
        for path in project_dir.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".swe_local_agent" not in path.parts
        and path.name not in INTERNAL_CONTEXT_FILES
    ]

    for rel_path in candidate_paths:
        if Path(rel_path).name in INTERNAL_CONTEXT_FILES:
            continue
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        file_path = project_dir / rel_path
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        context_parts.append(f"\n[FILE: {rel_path}]\n```text\n{content}\n```")
        if sum(len(part) for part in context_parts) >= max_chars:
            context_parts.append("\n[context truncated]")
            break

    return "\n".join(context_parts)

def build_metric_entry(agent: str, metrics_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not metrics_data:
        return None

    eval_count = int(metrics_data.get("eval_count") or 0)
    prompt_eval_count = int(metrics_data.get("prompt_eval_count") or 0)
    eval_duration_ns = int(metrics_data.get("eval_duration") or 0)
    prompt_eval_duration_ns = int(metrics_data.get("prompt_eval_duration") or 0)
    total_duration_ns = int(metrics_data.get("total_duration") or eval_duration_ns or 0)
    load_duration_ns = int(metrics_data.get("load_duration") or 0)
    eval_duration_seconds = eval_duration_ns / 1e9 if eval_duration_ns else 0.0
    duration_seconds = total_duration_ns / 1e9 if total_duration_ns else eval_duration_seconds
    tokens_sec = float(metrics_data.get("tokens_sec") or 0.0)
    if not tokens_sec and eval_count and eval_duration_seconds:
        tokens_sec = eval_count / eval_duration_seconds

    return {
        "agent": agent,
        "eval_count": eval_count,
        "prompt_eval_count": prompt_eval_count,
        "eval_duration_seconds": eval_duration_seconds,
        "prompt_eval_duration_seconds": prompt_eval_duration_ns / 1e9 if prompt_eval_duration_ns else 0.0,
        "duration_seconds": duration_seconds,
        "load_duration_seconds": load_duration_ns / 1e9 if load_duration_ns else 0.0,
        "tokens_sec": tokens_sec,
    }

def append_metric(metrics: Optional[List[Dict[str, Any]]], agent: str, metrics_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metric_list = list(metrics or [])
    entry = build_metric_entry(agent, metrics_data)
    if entry:
        metric_list.append(entry)
    return metric_list

def format_metric_entry(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return ""
    return (
        f"Tempo: {entry.get('duration_seconds', 0.0):.2f}s | "
        f"Tokens resposta: {entry.get('eval_count', 0)} | "
        f"Tokens prompt: {entry.get('prompt_eval_count', 0)} | "
        f"Média: {entry.get('tokens_sec', 0.0):.1f} TPS"
    )

def format_metrics_footer(entry: Optional[Dict[str, Any]]) -> str:
    metric_text = format_metric_entry(entry)
    if not metric_text:
        return ""
    return f"\n\n---\n*{metric_text}*"

def format_workflow_totals(metrics: Optional[List[Dict[str, Any]]]) -> str:
    valid_metrics = [metric for metric in metrics or [] if isinstance(metric, dict)]
    if not valid_metrics:
        return ""

    total_seconds = sum(float(metric.get("duration_seconds") or 0.0) for metric in valid_metrics)
    total_eval_tokens = sum(int(metric.get("eval_count") or 0) for metric in valid_metrics)
    total_prompt_tokens = sum(int(metric.get("prompt_eval_count") or 0) for metric in valid_metrics)
    total_eval_seconds = sum(float(metric.get("eval_duration_seconds") or 0.0) for metric in valid_metrics)
    avg_tps = (total_eval_tokens / total_eval_seconds) if total_eval_seconds else 0.0

    return (
        "Workflow: Totais "
        f"(Tempo: {total_seconds:.2f}s | Tokens resposta: {total_eval_tokens} | "
        f"Tokens prompt: {total_prompt_tokens} | Média: {avg_tps:.1f} TPS)"
    )

async def planner_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Planner Node (PM & Tech Lead roles).
    Generates or refines implementation_plan.md.
    """
    project_id = state["project_id"]
    prompt = state["prompt"]
    feedback = state.get("user_feedback")
    version = state.get("plan_version", "1.0")
    history = state.get("log_messages", [])

    if state.get("plan_approved", False):
        return {
            "plan_version": version,
            "plan_content": state.get("plan_content", ""),
            "current_step": state.get("current_step", "coding"),
            "log_messages": history,
            "user_feedback": None
        }
    
    # Retrieve config context
    configurable = config.get("configurable", {}) if config else {}
    queue = configurable.get("queue")
    sandbox = configurable.get("sandbox")
    ollama = configurable.get("ollama")
    PLANNER_MODEL = configurable.get("model_planner")
    if queue:
        await queue.put({"event": "status", "data": "Preparando Planner Agent e contexto do workspace..."})
    if not configurable.get("models_resolved"):
        available = await get_available_models()
        PLANNER_MODEL = resolve_model(PLANNER_MODEL, available) or resolve_model(DEFAULT_PLANNER_MODEL, available) or DEFAULT_PLANNER_MODEL
    project_dir = sandbox.validate_path(project_id, ".")
    workspace_context = collect_workspace_context(
        project_dir,
        [],
        max_chars=PLANNER_WORKSPACE_CONTEXT_MAX_CHARS,
    )

    if queue:
        await queue.put({"event": "status", "data": f"Iniciando Planner Agent ({PLANNER_MODEL})..."})

    # Increment version if feedback is present
    if feedback and feedback.strip():
        try:
            v_num = float(version)
            version = f"{v_num + 1.0:.1f}"
        except ValueError:
            version = "2.0"

    system_prompt = (
        "Responda em Português do Brasil.\n"
        "Você é o Planner Agent. Crie um plano de implementação em Markdown.\n\n"
        "O plano DEVE conter:\n"
        "1. Escopo entendido: uma frase dizendo qual app será construído, preservando o domínio do pedido original.\n"
        "2. Funcionalidades mínimas obrigatórias: 2 a 5 itens concretos que a entrega precisa cumprir.\n"
        "3. Fora de escopo: o que não deve ser substituído, inventado ou ampliado nesta versão.\n"
        "4. Arquitetura e dependências.\n"
        "5. Lista de arquivos com caminhos relativos (ex: src/main.py), descrevendo propósito e comportamento esperado.\n"
        "6. Critérios de aceite para o Developer Agent validar.\n\n"
        "Regras:\n"
        "- Apenas planeje. Quem escreve código é o Developer Agent.\n"
        "- Preserve o domínio do pedido original; não substitua a tarefa por outro tipo de app mais simples.\n"
        "- Se o usuário pedir controle de atividades, tarefas, contatos, estoque ou domínio semelhante, mantenha esse domínio explicitamente nas funcionalidades mínimas e critérios de aceite.\n"
        "- Seja extremamente breve, conciso e direto. Evite introduções longas ou explicações extensas.\n"
        "- Use tópicos curtos (bullet points) para listar os itens e simplificar o plano.\n"
        "- Não inclua blocos de código, JSON, conteúdo de README ou blocos [FILE:].\n"
        "- Não escreva linhas de implementação como import, from, def, class, print, if, for, while, return, self.*, chamadas de função ou atribuições.\n"
        "- Se precisar citar lógica, descreva em linguagem natural; não escreva algoritmos nem pseudocódigo executável.\n"
        "- Não inclua README.md na lista de arquivos a menos que o usuário peça explicitamente.\n"
        "- Para tarefas simples de terminal, prefira um único arquivo principal com funções limpas.\n"
        "- Evite modularização excessiva ou criação de pastas/arquivos extras para tarefas simples. Prefira simplificar a estrutura para o mínimo de arquivos possível para reduzir o número total de tokens que o Developer Agent terá de escrever.\n"
        "- Para tarefas pequenas, liste 1 ou 2 arquivos; use 3 no máximo se houver configuração persistente ou domínio claramente separado.\n"
        "- Não liste arquivos opcionais; se algo for opcional, deixe fora do plano v1.0.\n"
        "- Não proponha MVC, camadas, controllers, interfaces ou modelos separados para apps simples de terminal.\n"
        "- Não invente aleatoriedade, simulações, timers, Pomodoro ou abstrações que o usuário não pediu.\n"
        "- Limite o plano a até 220 palavras, 3 arquivos e 4 critérios de aceite.\n"
        "- Seja compacto: liste apenas decisões e critérios que afetam a implementação.\n"
        "- Use o contexto do workspace como fonte de verdade. Não invente dependências ou comandos.\n"
        "- Comece o plano com '# Plano de Implementação'.\n"
    )

    workspace_block = (
        f"\n\nWorkspace atual:\n{workspace_context}\n"
        if workspace_context.strip()
        else "\n\nWorkspace atual: nenhum arquivo existente.\n"
    )
    if feedback and feedback.strip():
        user_prompt = (
            f"Prompt Inicial: {prompt}\n\n"
            f"{workspace_block}\n"
            f"Plano Atual (v{state.get('plan_version')}):\n"
            f"{state.get('plan_content')}\n\n"
            f"Feedback do Usuário: {feedback}\n\n"
            f"Atualize o plano para v{version} incorporando o feedback."
        )
    else:
        user_prompt = (
            f"Solicitação: {prompt}\n\n"
            f"{workspace_block}\n"
            f"Crie o plano de implementação v1.0."
        )

    # Stream the Planner response to the queue
    plan_content = ""
    thinking_content = ""
    metrics_data = None
    async for chunk in ollama.stream_generate(
        PLANNER_MODEL,
        user_prompt,
        system=system_prompt,
        options=PLANNER_RUNTIME_OPTIONS,
    ):
        if chunk.get("type") == "thinking":
            thinking_content += chunk["content"]
            if queue:
                await queue.put({"event": "token", "type": "thinking", "data": chunk["content"]})
        elif chunk.get("type") == "response":
            plan_content += chunk["content"]
            if queue:
                await queue.put({"event": "token", "type": "response", "data": chunk["content"]})
        elif chunk.get("type") == "metrics":
            metrics_data = chunk
        elif chunk.get("type") == "error":
            return {"errors": [chunk["content"]], "current_step": "planning"}

    if not plan_content.strip():
        fallback_plan = strip_metrics_footer(thinking_content)
        if looks_like_implementation_plan(fallback_plan):
            plan_content = fallback_plan
            history.append("Planner Agent: resposta final vazia; plano recuperado da avaliação inicial do Project Manager.")
            if queue:
                await queue.put({
                    "event": "status",
                    "data": "Planner retornou resposta final vazia; usando o plano estruturado gerado na avaliação inicial."
                })
                await queue.put({"event": "token", "type": "response", "data": plan_content})
        else:
            error_msg = (
                "Planner Agent retornou apenas Reasoning Stream ou conteúdo vazio, sem plano final em Markdown. "
                "Tente novamente ou selecione um modelo não-raciocinador para Planner."
            )
            logger.warning(
                "Planner produced empty final response for project %s. Thinking chars: %s",
                project_id,
                len(thinking_content),
            )
            history.append(f"Planner Agent: Falha ao gerar plano final. {error_msg}")
            if queue:
                await queue.put({"event": "status", "data": error_msg})
            return {
                "plan_content": "",
                "current_step": "planning",
                "errors": [error_msg],
                "log_messages": history,
            }

    plan_content, removed_code_blocks = sanitize_planner_output(plan_content)
    quality_checks = build_quality_checks(
        prompt,
        plan_content,
        removed_code_blocks=removed_code_blocks,
        stage="planner",
    )
    if removed_code_blocks:
        warning_msg = (
            f"Planner Agent: {removed_code_blocks} bloco(s) de código removido(s) do plano. "
            "Código deve ser gerado apenas pelo Developer Agent."
        )
        history.append(warning_msg)
        if queue:
            await queue.put({"event": "status", "data": warning_msg})

    # Yield metrics back to the client at the end of execution
    metrics = state.get("metrics", [])
    metric_entry = build_metric_entry("Planner Agent", metrics_data)
    metrics = append_metric(metrics, "Planner Agent", metrics_data)
    metrics_msg = ""
    if metrics_data:
        metrics_msg = format_metrics_footer(metric_entry)
        if queue:
            await queue.put({"event": "token", "type": "response", "data": metrics_msg})

    # Write plan to workspace
    plan_file_name = f"implementation_plan.md"
    plan_path = sandbox.validate_path(project_id, plan_file_name)
    
    # Ensure directory structure exists
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(plan_content)

    # Save state.json as well within workspaces
    state_dir = project_dir / ".swe_local_agent"
    state_dir.mkdir(exist_ok=True)
    
    # Save a simplified state to commit
    tracker_file = state_dir / "state.json"
    state_data = dict(state)
    state_data.update({
        "project_id": project_id,
        "prompt": prompt,
        "plan_version": version,
        "plan_content": plan_content,
        "current_step": "planning",
        "plan_approved": state["plan_approved"],
        "metrics": metrics,
        "quality_checks": quality_checks,
    })
    with open(tracker_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)

    # Commit silently in Git
    GitManager.init_repo(project_dir)
    GitManager.commit_state(project_dir, f"[Planner] Plano v{version} gerado")

    plan_log = f"Planner Agent: Plano de implementação v{version} gerado."
    if metric_entry:
        plan_log += f" ({format_metric_entry(metric_entry)})"
    history.append(plan_log)

    if queue:
        await queue.put({"event": "status", "data": f"Plano v{version} salvo no Workspace."})

    return {
        "plan_version": version,
        "plan_content": plan_content,
        "current_step": "planning",
        "log_messages": history,
        "metrics": metrics,
        "quality_checks": quality_checks,
        "user_feedback": None  # Clear feedback once processed
    }

async def developer_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Developer Node (Software Developer).
    Reads the approved plan, writes physical code files, and performs a lightweight self-review.
    """
    project_id = state["project_id"]
    plan_content = state["plan_content"]
    history = state.get("log_messages", [])
    files_created = state.get("files_created", [])
    errors = state.get("errors", [])
    configurable = config.get("configurable", {}) if config else {}
    queue = configurable.get("queue")
    sandbox = configurable.get("sandbox")
    ollama = configurable.get("ollama")
    DEVELOPER_MODEL = configurable.get("model_developer")
    if not configurable.get("models_resolved"):
        available = await get_available_models()
        DEVELOPER_MODEL = resolve_model(DEVELOPER_MODEL, available) or resolve_model(DEFAULT_DEVELOPER_MODEL, available) or DEFAULT_DEVELOPER_MODEL
    project_dir = sandbox.validate_path(project_id, ".")
    workspace_context = collect_workspace_context(
        project_dir,
        [],
        max_chars=DEVELOPER_WORKSPACE_CONTEXT_MAX_CHARS,
    )

    if queue:
        await queue.put({"event": "status", "data": f"Iniciando Developer Agent ({DEVELOPER_MODEL})..."})

    system_prompt = (
        "Responda em Português do Brasil.\n"
        "Você é o Developer Agent. Escreva os arquivos usando exatamente este formato:\n"
        "[FILE: caminho/do/arquivo.ext]\n"
        "```linguagem\n"
        "código\n"
        "```\n\n"
        "Regras:\n"
        "- Siga estritamente a stack pedida pelo usuário.\n"
        "- A solicitação original do usuário tem prioridade sobre simplificações indevidas do plano.\n"
        "- Não substitua o domínio pedido por outro app menor ou mais fácil. Exemplo: se o pedido for controle de atividades, não entregue Pomodoro, timer ou cronômetro.\n"
        "- Implemente todos os critérios de aceite e funcionalidades mínimas listados no plano.\n"
        "- Se o plano estiver ambíguo, preserve o escopo original do usuário.\n"
        "- Baseie-se no workspace atual; não invente dependências ou comandos.\n"
        "- Não gere arquivo README.md a menos que o usuário peça explicitamente.\n"
        "- Para tarefas novas e simples de terminal, prefira um único arquivo principal com funções limpas.\n"
        "- Só divida em múltiplos arquivos quando isso reduzir complexidade real ou for pedido explicitamente.\n"
        "- Gere todos os arquivos listados no plano aprovado. Se o plano listar main.py, main.py é obrigatório.\n"
        "- Para aplicações Python de terminal, main.py deve ser o ponto de entrada executável.\n"
        "- Comece a resposta imediatamente pelo primeiro bloco [FILE:].\n"
        "- O nome do arquivo deve estar na linha [FILE:], nunca dentro de um bloco de código separado.\n"
        "- Não coloque comentários como '# arquivo.py' para indicar nome de arquivo; use somente a linha [FILE: arquivo.py].\n"
        "- Use a extensão real do código. Para código Python, use sempre .py; nunca use .txt para código-fonte.\n"
        "- Escreva código limpo, enxuto e livre de comentários longos ou prolixos para reduzir o número total de tokens gerados.\n"
        "- Seja extremamente direto. Não faça explicações, conversações, introduções ou considerações antes ou depois do código. Sua resposta deve conter apenas os blocos dos arquivos, encerrando-se assim que o último bloco for fechado.\n"
    )

    user_prompt = (
        f"Solicitação original do usuário:\n{state.get('prompt', '')}\n\n"
        f"Plano de Implementação Aprovado:\n```markdown\n{plan_content}\n```\n\n"
        "Contexto atual do Workspace (fonte de verdade; preserve linguagem, arquivos e comandos coerentes com este conteúdo):\n"
        f"{workspace_context if workspace_context.strip() else 'Nenhum arquivo de projeto relevante encontrado.'}\n\n"
        "Gere agora apenas os blocos [FILE:] necessários para cumprir o plano."
    )
    if errors:
        user_prompt += f"\n\nA execução anterior encontrou problemas. Corrija com base nos pontos abaixo:\n"
        user_prompt += "\n".join(errors)

    dev_output = ""
    metrics_data = None
    streamed_file_paths = set()

    async def persist_extracted_files(extracted_files: List[Tuple[str, str]], only_new: bool = False) -> List[str]:
        written_now = []
        for filepath, filecontent in extracted_files:
            already_streamed = filepath in streamed_file_paths
            if only_new and already_streamed:
                continue

            resolved_path = sandbox.validate_path(project_id, filepath)
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(filecontent)

            streamed_file_paths.add(filepath)
            if filepath not in files_created:
                files_created.append(filepath)
            written_now.append(filepath)

            if queue and not already_streamed:
                await queue.put({"event": "status", "data": f"Escrito: {filepath}"})
                await queue.put({"event": "files_changed", "files": list(files_created), "latest": filepath})

        if written_now:
            write_state_snapshot(project_dir, state, {
                "current_step": "coding",
                "files_created": files_created,
                "log_messages": history,
                "errors": [],
                "plan_approved": True,
                "metrics": state.get("metrics", []),
                "quality_checks": state.get("quality_checks", {}),
            })
        return written_now

    async for chunk in ollama.stream_generate(
        DEVELOPER_MODEL,
        user_prompt,
        system=system_prompt,
        options=DEVELOPER_RUNTIME_OPTIONS,
    ):
        if chunk.get("type") == "response":
            dev_output += chunk["content"]
            if queue:
                await queue.put({"event": "token", "type": "response", "data": chunk["content"]})
            try:
                await persist_extracted_files(parse_files_from_output(dev_output), only_new=True)
            except ValueError as e:
                if queue:
                    await queue.put({"event": "status", "data": f"Erro de segurança: {str(e)}"})
                return {"errors": [str(e)], "current_step": "failed"}
        elif chunk.get("type") == "metrics":
            metrics_data = chunk
        elif chunk.get("type") == "error":
            return {"errors": [chunk["content"]], "current_step": "failed"}

    metrics = state.get("metrics", [])
    metric_entry = build_metric_entry("Developer Agent", metrics_data)
    metrics = append_metric(metrics, "Developer Agent", metrics_data)
    metric_text = format_metric_entry(metric_entry)
    if metrics_data:
        metrics_msg = format_metrics_footer(metric_entry)
        if queue:
            await queue.put({"event": "token", "type": "response", "data": metrics_msg})

    # Extract files
    extracted_files = parse_files_from_output(dev_output)
    if not extracted_files:
        debug_rel_path = save_agent_debug_output(project_dir, "last_developer_output.txt", dev_output)
        if queue:
            await queue.put({
                "event": "status",
                "data": f"Aviso: Nenhum bloco de arquivo detectado na saída do Developer. Saída salva em {debug_rel_path}."
            })
        fail_msg = "Developer Agent: Falha ao extrair blocos de arquivos estruturados."
        if metric_text:
            fail_msg += f" ({metric_text})"
        history.append(fail_msg)
        history.append(f"Developer Agent: Saída bruta salva em {debug_rel_path}.")
        write_state_snapshot(project_dir, state, {
            "current_step": "failed",
            "files_created": files_created,
            "log_messages": history,
            "errors": ["Formato de arquivo inválido retornado pelo Developer."],
            "plan_approved": True,
            "metrics": metrics,
        })
        return {
            "current_step": "failed",
            "errors": ["Formato de arquivo inválido retornado pelo Developer."],
            "log_messages": history,
            "metrics": metrics,
        }

    # Write files safely once more using the final complete content.
    try:
        await persist_extracted_files(extracted_files, only_new=False)
    except ValueError as e:
        if queue:
            await queue.put({"event": "status", "data": f"Erro de segurança: {str(e)}"})
        return {"errors": [str(e)], "current_step": "failed"}

    quality_checks = build_quality_checks(
        state.get("prompt", ""),
        plan_content,
        removed_code_blocks=int((state.get("quality_checks") or {}).get("planner_code_removed_blocks") or 0),
        files_created=files_created,
        developer_output=dev_output,
        stage="developer",
    )

    dev_msg = f"Developer Agent: Escreveu {len(extracted_files)} arquivo(s) e concluiu a codificação."
    if metric_text:
        dev_msg += f" ({metric_text})"
    history.append(dev_msg)
    if queue:
        await queue.put({"event": "status", "data": "Developer Agent concluiu a codificação."})

    write_state_snapshot(project_dir, state, {
        "current_step": "completed",
        "files_created": files_created,
        "log_messages": history,
        "errors": [],
        "plan_approved": True,
        "metrics": metrics,
        "quality_checks": quality_checks,
    })

    # Commit silently
    GitManager.commit_state(project_dir, f"[Developer] Escreveu arquivos: {', '.join([f[0] for f in extracted_files])}")

    return {
        "current_step": "completed",
        "files_created": files_created,
        "log_messages": history,
        "metrics": metrics,
        "quality_checks": quality_checks,
        "errors": [] # Clear errors since we just rewrote/patched the code
    }

# Building the StateGraph
workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("developer", developer_node)
workflow.set_entry_point("planner")

def route_planner(state: AgentState):
    if state.get("plan_approved", False):
        return "developer"
    else:
        return END

workflow.add_conditional_edges("planner", route_planner, {"developer": "developer", END: END})
workflow.add_edge("developer", END)

compiled_graph = workflow.compile()
