"""GitHub identity is derived locally; no checkout path crosses the wire."""

from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from devlog.entity.Repository import Repository
from devlog.entity.TrackingError import TrackingError
from devlog.constants.DText import DText
from devlog.interface.Git import Git


class LocalRepository:
    def __init__(self, directory=None):
        result = subprocess.run(["git", "-C", str(directory or Path.cwd()), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise TrackingError("not_repository", DText.NOT_REPOSITORY)
        self.root = Path(result.stdout.strip()).resolve()
        self.git = Git(self.root)
        remote = self.git._git("remote", "get-url", "origin").stdout.strip()
        self.repository = Repository(self.identity(remote))

    @staticmethod
    def identity(remote):
        if "://" not in remote:
            match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
            if not match:
                raise TrackingError("invalid_remote", DText.INVALID_REMOTE)
            host, path = match.groups()
        else:
            parsed = urlsplit(remote)
            host, path = parsed.hostname, parsed.path.lstrip("/")
        path = path.rstrip("/").removesuffix(".git")
        if not host or host.lower() != "github.com" or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path) is None:
            raise TrackingError("invalid_remote", DText.INVALID_REMOTE)
        return f"github.com/{path.lower()}"

    def commit_details(self, revision):
        # --end-of-options prevents a supplied revision becoming a Git option.
        sha = self.git._git("rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}").stdout.strip()
        self.git._git("merge-base", "--is-ancestor", sha, "HEAD")
        message = self.git._git("show", "-s", "--format=%B", sha).stdout.strip()
        return sha, message

    def release_script(self):
        for name in ("new_release.sh", "scripts/new_release.sh", "scripts/new-release.sh"):
            path = self.root / name
            if path.is_file():
                return path
        return None
