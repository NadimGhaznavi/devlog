"""GitHub identity is derived locally; no checkout path crosses the wire."""

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from devlog.entity.Repository import Repository
from devlog.entity.TrackingError import TrackingError
from devlog.constants.DText import DText
from devlog.constants.DRelease import DRelease
from devlog.constants.DTracking import DTracking
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

    def release_tags(self, *, exclude=()):
        """Read local version tags; never fetch or change a ref.

        Annotated tags supply their tagger time. Lightweight tags have no
        creation time, so use the tagged commit's committer time instead.
        """
        result = self.git._git(
            "for-each-ref", "--format=%(refname:strip=2)%00%(objecttype)%00%(creatordate:iso-strict)%00%(contents:subject)%00",
            "refs/tags/",
        )
        releases = []
        for line in result.stdout.split("\0\n"):
            if not line:
                continue
            tag, object_type, timestamp, subject = line.split("\0", 3)
            if tag in exclude or re.fullmatch(DRelease.TAG_PATTERN, tag) is None:
                continue
            commit = self.git._git("rev-parse", "--verify", "--end-of-options", f"refs/tags/{tag}^{{commit}}", check=False)
            if commit.returncode:
                continue  # Version-like tags on trees/blobs are not releases.
            prefix = f"Release {tag.removeprefix('v')}: "
            codename = subject.removeprefix(prefix).strip() if object_type == "tag" and subject.startswith(prefix) else None
            releases.append({
                DRelease.TAG_NAME: tag, DRelease.CODENAME: codename or None,
                DTracking.COMMIT_SHA: commit.stdout.strip(),
                DRelease.RELEASED_AT: datetime.fromisoformat(timestamp).astimezone(timezone.utc).isoformat(),
            })
        return releases
