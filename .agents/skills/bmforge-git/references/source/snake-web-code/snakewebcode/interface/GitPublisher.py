"""Publish the homepage and static reports from a dedicated, serialized Git checkout."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile

from snakewebcode.constants.DSnakeWebCode import DSnakeWebCode


class GitPublisher:
    STATUS_PATH = "index.md"
    REPORT_PATH = "reports/experiment-highscores.html"
    HISTORY_PATH = "reports/data/experiment-highscores.csv"
    SCRIPT_PATH = "reports/experiment-highscores.js"
    DISTRIBUTION_PATH = "reports/score-distribution.html"
    DISTRIBUTION_SCRIPT_PATH = "reports/score-distribution.js"
    SCORES_PATH = "reports/data/run-scores.csv"
    TOP_RUNS_PATH = "reports/top-100.html"
    THINKING_PATH = "reports/ax3l-thinking.html"
    TOP_RUNS_SCRIPT_PATH = "reports/top-100.js"
    GOLDEN_PATH = "reports/golden-configurations.html"
    GOLDEN_DETAIL_PATH = "reports/golden-detail.html"
    GOLDEN_SCRIPT_PATH = "reports/golden-configurations.js"
    GOLDEN_HISTORY_PATH = "reports/data/golden-configurations.csv"
    EVENT_PATH = "reports/event-log.html"
    EVENT_DETAIL_PATH = "reports/event-detail.html"
    EVENT_SCRIPT_PATH = "reports/event-log.js"
    CSV_SCRIPT_PATH = "reports/report-csv.js"
    EVENT_HISTORY_PATH = "reports/data/events.csv"
    EVENT_SIMULATIONS_PATH = "reports/data/event-simulations.csv"
    EVENT_CURSOR_PATH = "reports/data/event-export.json"
    DAILY_PATH = "reports/data/daily-games.json"
    DAILY_SCRIPT_PATH = "reports/daily-games.js"
    PROGRESS_PATH = "reports/data/daily-progress.json"
    PROGRESS_GIF_PATH = "reports/games/daily-progress.gif"
    # Keep the retired frame sheet managed for failed-push retries and site resets.
    PROGRESS_SPRITE_PATH = "reports/games/daily-progress.png"
    DAILY_GIF_PATHS = tuple(f"reports/games/daily-{rank}.gif"
                           for rank in range(1, DSnakeWebCode.DAILY_GAME_LIMIT + 1))
    OWNED_PATHS = (STATUS_PATH, REPORT_PATH, HISTORY_PATH, SCRIPT_PATH,
                   DISTRIBUTION_PATH, DISTRIBUTION_SCRIPT_PATH, SCORES_PATH,
                   TOP_RUNS_PATH, TOP_RUNS_SCRIPT_PATH, THINKING_PATH,
                   GOLDEN_PATH, GOLDEN_SCRIPT_PATH, GOLDEN_HISTORY_PATH, GOLDEN_DETAIL_PATH,
                   EVENT_PATH, EVENT_DETAIL_PATH, EVENT_SCRIPT_PATH, CSV_SCRIPT_PATH,
                   EVENT_HISTORY_PATH, EVENT_SIMULATIONS_PATH, EVENT_CURSOR_PATH,
                   DAILY_PATH, DAILY_SCRIPT_PATH, *DAILY_GIF_PATHS,
                   PROGRESS_PATH, PROGRESS_GIF_PATH, PROGRESS_SPRITE_PATH)

    def __init__(self, checkout, branch="main"):
        self.checkout = Path(checkout).resolve()
        self.branch = branch
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

    def _ancestor(self, first, second):
        result = self._git("merge-base", "--is-ancestor", first, second, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError("Cannot compare publishing branch history")
        return result.returncode == 0

    @contextmanager
    def session(self):
        top = Path(self._git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if top != self.checkout:
            raise RuntimeError("Publishing checkout must be the repository root")
        git_dir = Path(self._git("rev-parse", "--absolute-git-dir").stdout.strip())
        with (git_dir / "snake-web-publish.lock").open("a") as lock:
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
            # Only retry unpublished commits whose changes are confined to the managed publication files.
            commits = self._git("rev-list", "FETCH_HEAD..HEAD").stdout.splitlines()
            for commit in commits:
                parents = self._git("rev-list", "--parents", "-n", "1", commit).stdout.split()
                paths = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines()
                if len(parents) != 2 or not paths or not set(paths).issubset(self.OWNED_PATHS):
                    raise RuntimeError("Unpublished commits must change only the homepage and managed reports")
            yield

    def _status_file(self):
        path = self.checkout / self.STATUS_PATH
        if path.resolve() != path or not path.is_file():
            raise RuntimeError("Homepage must be an existing file without symlinks")
        self._git("ls-files", "--error-unmatch", "--", self.STATUS_PATH)
        return path

    def read_status(self):
        return self._status_file().read_text(encoding='utf-8', errors='replace')

    def read_history(self, name=None):
        path = self._managed_file(name or self.HISTORY_PATH)
        return path.read_text() if path.exists() else ''

    def read_bytes(self, name):
        path = self._managed_file(name)
        return path.read_bytes() if path.exists() else b''

    def _managed_file(self, name):
        if name not in self.OWNED_PATHS:
            raise ValueError('Not a managed publishing path')
        path = self.checkout / name
        if path.resolve() != path or (path.exists() and not path.is_file()):
            raise RuntimeError('Publishing paths must be regular files without symlinks')
        return path

    def publish(self, content, reports=None):
        self._status_file()
        files = {self.STATUS_PATH: content, **(reports or {})}
        paths = {name: self._managed_file(name) for name in files}
        changed = []
        for name, value in files.items():
            path = paths[name]
            data = value if isinstance(value, bytes) else value.encode('utf-8')
            if path.exists() and path.read_bytes() == data:
                continue
            self._write_file(path, value)
            changed.append(name)
        if changed:
            self._git('add', '--', *changed)
            self._git('commit', '-m', 'Update experiment status and reports', '--', *changed)
        pending = self._git("rev-list", "--count", "FETCH_HEAD..HEAD").stdout.strip() != "0"
        if pending:
            self._git("push", "origin", f"HEAD:refs/heads/{self.branch}")
        return pending

    def _write_file(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode('utf-8')
        if not path.exists() or path.read_bytes() != data:
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
