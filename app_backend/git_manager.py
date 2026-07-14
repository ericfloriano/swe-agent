import os
import git
from pathlib import Path
from typing import List, Dict, Any

LEGACY_WORKSPACE_README = "# SWE Local Agent Workspace\n\nEste diretório contém código gerado de forma autônoma.\n"

class GitManager:
    @staticmethod
    def init_repo(repo_path: Path) -> git.Repo:
        """
        Initializes a git repository at the given path if it doesn't already exist.
        Ensures an initial commit exists.
        """
        repo_path_resolved = repo_path.resolve()
        if not (repo_path_resolved / ".git").exists():
            repo = git.Repo.init(repo_path_resolved)

            # Configure local dummy credentials for commits to succeed without global config errors
            with repo.config_writer() as cw:
                cw.set_value("user", "name", "SWE Local Agent")
                cw.set_value("user", "email", "agent@swelocalagent.local")

            return repo
        else:
            repo = git.Repo(repo_path_resolved)
            # Ensure dummy config is set locally
            with repo.config_writer() as cw:
                cw.set_value("user", "name", "SWE Local Agent")
                cw.set_value("user", "email", "agent@swelocalagent.local")
            return repo

    @staticmethod
    def remove_legacy_workspace_readme(repo_path: Path) -> bool:
        """
        Removes the old automatic workspace README, preserving any real project README.
        """
        readme_path = repo_path.resolve() / "README.md"
        if not readme_path.exists() or not readme_path.is_file():
            return False
        try:
            if readme_path.read_text(encoding="utf-8") == LEGACY_WORKSPACE_README:
                readme_path.unlink()
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def commit_state(repo_path: Path, message: str, author_name: str = "SWE Local Agent") -> str:
        """
        Stages all changes (including untracked files) and commits them.
        Returns the new commit SHA.
        """
        repo = git.Repo(repo_path.resolve())
        # git add -A
        repo.git.add(A=True)
        
        # Check if there are actual changes staged
        if not repo.is_dirty(untracked_files=True):
            # No changes to commit, return the latest commit SHA
            try:
                return repo.head.commit.hexsha
            except ValueError:
                return ""
            
        author = git.Actor(author_name, "agent@swelocalagent.local")
        commit = repo.index.commit(message, author=author, committer=author)
        return commit.hexsha

    @staticmethod
    def get_history(repo_path: Path) -> List[Dict[str, Any]]:
        """
        Returns the commit history log in reverse chronological order.
        """
        resolved_path = repo_path.resolve()
        if not (resolved_path / ".git").exists():
            return []
        try:
            repo = git.Repo(resolved_path)
            commits = list(repo.iter_commits())
            history = []
            for c in commits:
                history.append({
                    "sha": c.hexsha,
                    "short_sha": c.hexsha[:7],
                    "message": c.message.strip(),
                    "author": c.author.name,
                    "date": c.committed_datetime.isoformat(),
                })
            return history
        except Exception:
            return []

    @staticmethod
    def rollback(repo_path: Path, sha: str) -> None:
        """
        Performs a hard rollback to the specified SHA and cleans up untracked files.
        """
        repo = git.Repo(repo_path.resolve())
        # Revert all tracked files to the target commit
        repo.git.reset("--hard", sha)
        # Clean any untracked files/folders created after that commit
        repo.git.clean("-fd")
