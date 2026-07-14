import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List

from app_backend.agent_orchestrator import (
    build_quality_checks,
    collect_workspace_context,
    parse_files_from_output,
    get_available_models,
    resolve_model,
)
from app_backend.git_manager import GitManager
from app_backend.ollama_client import OllamaClient
from app_backend.security import SecuritySandbox


ROOT_DIR = Path(__file__).resolve().parents[1]
WORKSPACES_ROOT = ROOT_DIR / "workspaces"
INTERNAL_CONTEXT_FILES = {"implementation_plan.md"}



async def run_model(
    ollama: OllamaClient,
    model: str,
    system_prompt: str,
    user_prompt: str,
    show_thinking: bool,
) -> str:
    response_text = ""
    async for chunk in ollama.stream_generate(model, user_prompt, system=system_prompt):
        chunk_type = chunk.get("type")
        content = chunk.get("content", "")
        if chunk_type == "thinking" and show_thinking:
            print(content, end="", flush=True)
        elif chunk_type == "response":
            response_text += content
            print(content, end="", flush=True)
        elif chunk_type == "metrics":
            tokens_sec = chunk.get("tokens_sec", 0.0)
            eval_count = chunk.get("eval_count", 0)
            print(f"\n[metrics] tokens={eval_count} speed={tokens_sec:.1f} tps")
        elif chunk_type == "error":
            raise RuntimeError(content)
    print()
    return response_text.strip()


def write_state(project_dir: Path, state: Dict) -> None:
    state_dir = project_dir / ".swe_local_agent"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")



def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    raise SystemExit("Use --prompt or --prompt-file.")


async def run_cli(args: argparse.Namespace) -> None:
    WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
    sandbox = SecuritySandbox(str(WORKSPACES_ROOT))
    project_dir = sandbox.validate_path(args.workspace, ".")
    project_dir.mkdir(parents=True, exist_ok=True)
    GitManager.init_repo(project_dir)

    available_models = await get_available_models()
    planner_model = resolve_model(args.planner_model, available_models)
    developer_model = resolve_model(args.developer_model, available_models)
    prompt = read_prompt(args)
    ollama = OllamaClient()

    print(f"[workspace] {project_dir}")
    print(f"[planner] {planner_model}")
    planner_system = (
        "You are the Planner Agent of an offline SWE CLI. "
        "Create a concise implementation plan in Markdown. "
        "You are not the Developer Agent: do not write source code, final README content, JSON files, [FILE:] blocks, or fenced code blocks. "
        "For each file, describe purpose, responsibilities, expected behavior, and validation points only. "
        "The final plan must be outside <think> tags and start with '# Implementation Plan'."
    )
    planner_prompt = (
        "User request:\n"
        f"{prompt}\n\n"
        "Current workspace context. Use this as the source of truth for modification or documentation tasks:\n"
        f"{collect_workspace_context(project_dir, [], max_chars=60000) or 'No existing project files.'}\n\n"
        "Return architecture, files to create, validation strategy, and acceptance criteria."
    )
    plan = await run_model(ollama, planner_model, planner_system, planner_prompt, args.show_thinking)
    if not plan.strip():
        raise SystemExit("Planner returned an empty plan.")
    quality_checks = build_quality_checks(prompt, plan, stage="planner")

    plan_path = sandbox.validate_path(args.workspace, "implementation_plan.md")
    plan_path.write_text(plan + "\n", encoding="utf-8")
    state = {
        "project_id": args.workspace,
        "prompt": prompt,
        "plan_version": "1.0",
        "plan_content": plan,
        "plan_approved": False,
        "current_step": "planning",
        "files_created": [],
        "errors": [],
        "log_messages": [f"CLI Planner generated a plan with {len(plan)} chars."],
        "model_planner": planner_model,
        "model_developer": developer_model,
        "quality_checks": quality_checks,
    }
    write_state(project_dir, state)
    GitManager.commit_state(project_dir, "[CLI Planner] Plan generated")

    if not args.auto_approve:
        answer = input("Approve plan and run Developer Agent? [y/N] ").strip().lower()
        if answer not in {"y", "yes", "s", "sim"}:
            print("[done] Plan saved. Developer was not started.")
            return

    print(f"[developer] {developer_model}")
    developer_system = (
        "You are the Developer Agent of an offline SWE CLI. "
        "Write every source file using exactly this format:\n"
        "[FILE: path/to/file]\n```language\ncontent\n```\n"
        "Use the stack requested by the user. If the user asks for Node.js/Express, "
        "write JavaScript with Express and never Flask/Python in .js files. "
        "For README/documentation or modification tasks, rely strictly on the current workspace context; "
        "do not invent runtimes, commands, dependencies, files, links, or documentation paths. "
        "Before finishing, perform a silent self-check for request adherence, missing files, wrong stack, obvious import errors, and documented commands. "
        "If the self-check finds a problem, fix the [FILE:] blocks before answering. "
        "The filename must be in the [FILE:] line, never as a comment inside a code block. "
        "For Python source code, use .py files and never .txt. "
        "Do not include long explanations outside file blocks."
    )
    developer_prompt = (
        f"Original request:\n{prompt}\n\n"
        f"Approved plan:\n{plan}\n\n"
        "Current workspace context:\n"
        f"{collect_workspace_context(project_dir, [], max_chars=80000) or 'No existing project files.'}\n\n"
        "Generate the implementation files now and apply the self-check before answering."
    )
    developer_output = await run_model(ollama, developer_model, developer_system, developer_prompt, args.show_thinking)
    files = parse_files_from_output(developer_output)
    if not files:
        state["errors"] = ["Developer returned no [FILE:] blocks."]
        state["current_step"] = "failed"
        write_state(project_dir, state)
        raise SystemExit("Developer returned no [FILE:] blocks.")

    files_created = []
    for rel_path, content in files:
        target = sandbox.validate_path(args.workspace, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        files_created.append(rel_path)
        print(f"[write] {rel_path}")

    state.update({
        "plan_approved": True,
        "current_step": "completed",
        "files_created": files_created,
        "errors": [],
        "quality_checks": build_quality_checks(
            prompt,
            plan,
            files_created=files_created,
            developer_output=developer_output,
            stage="developer",
        ),
        "log_messages": state["log_messages"] + [
            f"CLI Developer wrote {len(files_created)} file(s).",
            "CLI Developer completed self-check.",
        ],
    })
    write_state(project_dir, state)
    GitManager.commit_state(project_dir, "[CLI Developer] Files generated")

    print("[done] Files generated by Developer Agent with self-check.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline SWE agent CLI powered by local Ollama models.")
    parser.add_argument("--workspace", required=True, help="Workspace name under ./workspaces")
    parser.add_argument("--prompt", help="Task prompt")
    parser.add_argument("--prompt-file", help="Path to a text file containing the task prompt")
    parser.add_argument("--planner-model", default="llama3.2-3b-local", help="Ollama model for planning/reasoning")
    parser.add_argument("--developer-model", default="qwen2.5-coder-7b-local", help="Ollama model for code generation")
    parser.add_argument("--auto-approve", action="store_true", help="Run Developer Agent immediately after planning")
    parser.add_argument("--show-thinking", action="store_true", help="Print model reasoning stream when tags are available")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
