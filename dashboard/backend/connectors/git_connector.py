"""Report Git metadata when present, or an explicitly unversioned source tree."""

import subprocess
from pathlib import Path


class GitConnector:
    def __init__(self, repository_path):
        self.repository_path = Path(repository_path).expanduser().resolve()

    def scan(self):
        result = {"repository": str(self.repository_path), "frozen": []}

        if not self.repository_path.is_dir():
            return {**result, "status": "ERROR", "error": "Quellverzeichnis fehlt."}

        # Git archives deliberately omit .git. This is a valid deployment mode,
        # not a broken architecture. A .git file also counts (linked worktree).
        git_marker = self.repository_path / ".git"
        if not git_marker.exists() and not git_marker.is_symlink():
            return {**result, "status": "SOURCE_ONLY", "git_available": False}

        try:
            tags = subprocess.check_output(
                ["git", "tag"],
                text=True,
                cwd=self.repository_path,
                stderr=subprocess.STDOUT,
            ).splitlines()
        except (OSError, subprocess.CalledProcessError) as exc:
            return {**result, "status": "ERROR", "error": str(exc)}

        return {
            **result,
            "status": "READY",
            "git_available": True,
            "frozen": [tag for tag in tags if "FROZEN" in tag],
        }
