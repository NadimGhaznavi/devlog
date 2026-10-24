from pathlib import Path
import subprocess

import pytest

from conftest import dl, git
from devlog.activity.CommitTask import CommitRecordingError, CommitTask
from devlog.interface.Git import Git
from devlog.interface.LocalRepository import LocalRepository


def test_commit_callback_runs_before_push_and_stages_root(checkout):
    root, remote = checkout
    (root / "new file").write_text("new\n")
    initial = git(remote, "rev-parse", "main").stdout.strip()
    observed = []

    def completed(sha):
        observed.append(sha)
        assert git(remote, "rev-parse", "main").stdout.strip() == initial
        assert (root / "new file").exists()

    Git(root).commit('message with "quotes" and $(literal)', on_committed=completed)
    assert observed == [git(root, "rev-parse", "HEAD").stdout.strip()]
    assert git(remote, "rev-parse", "main").stdout.strip() == observed[0]
    assert "new file" in git(root, "show", "--format=", "--name-only", "HEAD").stdout


def test_rejected_push_keeps_local_commit_and_callback(checkout):
    root, remote = checkout
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    (root / "change").write_text("change\n")
    recorded = []
    with pytest.raises(RuntimeError, match="Git push failed"):
        Git(root).commit("done", on_committed=recorded.append)
    assert recorded == [git(root, "rev-parse", "HEAD").stdout.strip()]
    assert git(remote, "rev-parse", "main").stdout.strip() != recorded[0]


def test_empty_commit_does_not_complete_task(checkout):
    root, _ = checkout
    recorded = []
    with pytest.raises(RuntimeError, match="Git commit failed"):
        Git(root).commit("empty", on_committed=recorded.append)
    assert recorded == []


def test_tracking_failure_reports_existing_commit_without_pushing(checkout):
    root, remote = checkout
    initial = git(remote, "rev-parse", "main").stdout.strip()
    (root / "new").write_text("new\n")

    class FailedRecording:
        def call(self, method, payload):
            if payload["phase"] == "prepare":
                return {"task_id": 4, "status": "running"}
            raise ConnectionError("reply lost")

    with pytest.raises(CommitRecordingError) as error:
        CommitTask(LocalRepository(root), FailedRecording()).run("local commit")
    assert error.value.commit_sha == git(root, "rev-parse", "HEAD").stdout.strip()
    assert error.value.commit_sha != initial
    assert git(remote, "rev-parse", "main").stdout.strip() == initial


def test_service_preflight_failure_leaves_git_untouched(checkout):
    root, _ = checkout
    before = git(root, "rev-parse", "HEAD").stdout
    (root / "untracked").write_text("untracked\n")

    class Unavailable:
        def call(self, *args):
            raise ConnectionError("offline")

    with pytest.raises(ConnectionError):
        CommitTask(LocalRepository(root), Unavailable()).run("never committed")
    assert git(root, "rev-parse", "HEAD").stdout == before
    assert git(root, "status", "--porcelain").stdout == "?? untracked\n"


@pytest.mark.parametrize("remote", ["git@github.com:Owner/Repo.git", "https://github.com/owner/repo", "ssh://git@github.com/OWNER/REPO.git"])
def test_repository_identity_ignores_clone_location(remote):
    assert LocalRepository.identity(remote) == "github.com/owner/repo"


def test_managed_publication_retains_template_behavior(checkout):
    root, remote = checkout
    # The publication component fetches origin, so use the disposable remote for this test.
    git(root, "remote", "set-url", "origin", str(remote))
    interface = Git(root, managed_paths=("report.html",))
    assert interface.publish({"report.html": "first"}, "report") is True
    before = git(root, "rev-parse", "HEAD").stdout
    assert interface.publish({"report.html": "first"}, "unchanged") is False
    assert git(root, "rev-parse", "HEAD").stdout == before
    with pytest.raises(ValueError):
        interface.publish({"other.html": "not allowed"}, "wrong")


@pytest.mark.database
def test_real_cli_commit_and_recovery(service, checkout, tasks):
    root, remote = checkout
    subdir = root / "nested"
    subdir.mkdir()
    assert dl(subdir, service, "start").returncode == 0
    task = tasks.prepare_commit("github.com/example/project")
    (root / "change").write_text("change\n")
    result = dl(subdir, service, "commit", 'Finished "task"')
    assert result.returncode == 0, result.stderr
    sha = git(root, "rev-parse", "HEAD").stdout.strip()
    assert sha in result.stdout
    assert tasks.prepare_commit("github.com/example/project", commit_sha=sha)["task_id"] == task["task_id"]
    assert git(remote, "rev-parse", "main").stdout.strip() == sha
    # A repeated recording acknowledges the same task without a duplicate Git commit.
    assert dl(root, service, "commit", "--record", sha).returncode == 0
    assert git(root, "rev-parse", "HEAD").stdout.strip() == sha


@pytest.mark.database
def test_real_cli_publish_passthrough_without_timer_changes(service, checkout, tasks):
    root, _ = checkout
    assert dl(root, service, "start").returncode == 0
    before = tasks.db.query("SELECT * FROM tracker_state")
    script = root / "new_release.sh"
    script.write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$1"\nexit 7\n')
    result = dl(root, service, "publish", "--", "release message")
    assert result.returncode == 7
    assert str(root) in result.stdout and "release message" in result.stdout
    assert tasks.db.query("SELECT * FROM tracker_state") == before
