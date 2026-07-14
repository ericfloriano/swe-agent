import os
import re
from pathlib import Path

# Patterns that represent dangerous shell commands
BLACKLISTED_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+-rf\b",       # Block recursive forced deletion
    r"\bmkfs\b",
    r"\bformat\b",
    r"\bchown\b",
    r"\bchmod\b",
    r"\bdd\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bcurl\b",          # Block external web fetches inside sandbox
    r"\bwget\b",
    r"\bnc\b",
    r"\bnetcat\b",
    r"\/dev\/",
]

# Only allow these commands to run
ALLOWED_COMMANDS = {"git", "python", "pytest"}

class SecuritySandbox:
    def __init__(self, workspaces_root: str):
        self.workspaces_root = Path(workspaces_root).resolve()

    def validate_path(self, project_id: str, target_path: str) -> Path:
        """
        Validates that target_path resolves strictly within workspaces_root / project_id.
        Raises ValueError if Path Traversal (escaping the workspace sandbox) is detected.
        """
        project_dir = (self.workspaces_root / project_id).resolve()
        
        # Ensure project directory is under workspaces_root
        if not project_dir.is_relative_to(self.workspaces_root) or project_dir == self.workspaces_root:
            raise ValueError("Security Error: Invalid project directory.")

        # Resolve path
        target_path_obj = Path(target_path)
        if target_path_obj.is_absolute():
            resolved_target = target_path_obj.resolve()
        else:
            resolved_target = (project_dir / target_path_obj).resolve()
        
        # Check that target is strictly within the project_dir (existing or not)
        if not resolved_target.is_relative_to(project_dir):
            raise ValueError(f"Security Error: Destination path {resolved_target} is outside the allowed project workspace.")
                
        return resolved_target

    def validate_command(self, command_str: str) -> bool:
        """
        Validates that a shell command is safe to execute.
        Returns True if safe, False otherwise.
        """
        clean_command = command_str.strip()
        if not clean_command:
            return False

        # 1. Check against blacklist patterns
        for pattern in BLACKLISTED_PATTERNS:
            if re.search(pattern, clean_command, re.IGNORECASE):
                return False

        # 2. Extract base command (first element before options)
        parts = clean_command.split()
        if not parts:
            return False

        # Extract name of command, e.g. "venv/bin/pytest" -> "pytest" or "python"
        main_cmd = parts[0]
        # Resolve command basename (e.g. ./venv/bin/pytest -> pytest)
        cmd_basename = os.path.basename(main_cmd)

        if cmd_basename not in ALLOWED_COMMANDS:
            return False

        # 3. Block path traversal attempts in command arguments
        if ".." in clean_command:
            return False

        return True
