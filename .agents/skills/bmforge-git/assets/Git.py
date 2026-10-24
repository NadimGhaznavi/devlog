"""Application-owned Git publishing and commit operations."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile


BMFORGE_COMPONENT = {"id": "bmforge.git", "spec_version": "0.1.0"}


class Git:
    def __init__(self, checkout, *, branch="main", managed_paths=()):
        self.checkout = Path(checkout).resolve()
        self.branch = branch
        self.managed_paths = frozenset(managed_paths)
        self._git("check-ref-format", f"refs/heads/{branch}")

    def _git(self, *args, check=True):
        result = subprocess.run(
            ["git", "-C", str(self.checkout), *args],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True, text=True, timeout=60,
        )
        if check and result.returncode:
            raise RuntimeError(f"Git {args[0]} failed: {result.stderr.strip()}")
        return result

    def _require_root(self):
        root = Path(self._git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if root != self.checkout:
            raise RuntimeError("Git checkout must be the repository root")

    def commit(self, message):
        """Commit every worktree change, then push using the current tracking branch."""
        self._require_root()
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Git commit message must not be empty")
        staged = self._git("add", ".", "-v")
        committed = self._git("commit", "-m", message)
        self._git("push")
        return staged.stdout, committed.stdout

    def _ancestor(self, first, second):
        result = self._git("merge-base", "--is-ancestor", first, second, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError("Cannot compare publishing branch history")
        return result.returncode == 0

    @contextmanager
    def _publication_session(self):
        self._require_root()
        git_dir = Path(self._git("rev-parse", "--absolute-git-dir").stdout.strip())
        with (git_dir / "bmforge-git-publish.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self._git("branch", "--show-current").stdout.strip() != self.branch:
                raise RuntimeError(f"Publishing checkout must be on {self.branch}")
            if self._git("status", "--porcelain", "--untracked-files=all").stdout:
                raise RuntimeError("Publishing checkout must be clean; inspect it before retrying")
            self._git("fetch", "--no-tags", "origin", f"refs/heads/{self.branch}")
            if self._ancestor("HEAD", "FETCH_HEAD"):
                self._git("merge", "--ff-only", "FETCH_HEAD")
            elif not self._ancestor("FETCH_HEAD", "HEAD"):
                raise RuntimeError("Publishing branch diverged; reconcile it before retrying")
            for commit in self._git("rev-list", "FETCH_HEAD..HEAD").stdout.splitlines():
                parents = self._git("rev-list", "--parents", "-n", "1", commit).stdout.split()
                paths = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines()
                if len(parents) != 2 or not paths or not set(paths).issubset(self.managed_paths):
                    raise RuntimeError("Unpublished commits must change only managed publishing files")
            yield

    def _managed_file(self, name):
        path = Path(name)
        if name not in self.managed_paths or path.is_absolute() or ".." in path.parts:
            raise ValueError("Not a managed publishing path")
        path = self.checkout / path
        if path.resolve() != path or (path.exists() and not path.is_file()):
            raise RuntimeError("Publishing paths must be regular files without symlinks")
        return path

    @staticmethod
    def _write_file(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def publish(self, files, message):
        """Commit changed managed files and push; retry an earlier failed push."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Git commit message must not be empty")
        with self._publication_session():
            paths = {name: self._managed_file(name) for name in files}
            changed = []
            for name, content in files.items():
                if not isinstance(content, (str, bytes)):
                    raise TypeError("Publishing content must be text or bytes")
                data = content.encode("utf-8") if isinstance(content, str) else content
                path = paths[name]
                if path.exists() and path.read_bytes() == data:
                    continue
                self._write_file(path, data)
                changed.append(name)
            if changed:
                self._git("add", "--", *changed)
                self._git("commit", "-m", message, "--", *changed)
            pending = self._git("rev-list", "--count", "FETCH_HEAD..HEAD").stdout.strip() != "0"
            if pending:
                self._git("push", "origin", f"HEAD:refs/heads/{self.branch}")
            return pending
