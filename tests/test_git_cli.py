from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from conftest import dl, git
from devlog import cli
from devlog.activity.CommitTask import CommitRecordingError, CommitTask
from devlog.interface.Git import Git
from devlog.interface.LocalRepository import LocalRepository
from devlog.zmq.ZMQServer import ZMQServer


@pytest.mark.parametrize("result,expected", [
    ({"task_id": None, "repository": None}, "No task currently running\n"),
    *[({"task_id": 17, "repository": "github.com/example/bmforge", "active_seconds": seconds},
       f"Repository (bmforge): Task #17 running for {duration} (HH:MM)\n")
      for seconds, duration in ((0, "00:00"), (59.999999, "00:00"), (60, "00:01"),
                                (9359, "02:35"), (371099, "103:04"))],
])
def test_cli_status_outside_repository_over_zmq(tmp_path, result, expected):
    @contextmanager
    def handler():
        def respond(request):
            assert request.method == "status"
            assert request.payload == {}
            return {"status": "ok", "result": result}
        yield respond

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        response = dl(tmp_path, {"environment": {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}},
                      "--server", server.endpoint, "status")
    assert response.returncode == 0, response.stderr
    assert response.stdout == expected


@pytest.mark.parametrize("paused_at,zone,expected", [
    ("2026-10-25T15:20:30.987654+00:00", "America/Toronto",
     "Repository (mycount): Task #12 paused on 2026-10-25 11:20:30\n"),
    ("2026-01-25T15:20:30+00:00", "America/Toronto",
     "Repository (mycount): Task #12 paused on 2026-01-25 10:20:30\n"),
    ("2026-10-25T15:20:30+00:00", "Asia/Kolkata",
     "Repository (mycount): Task #12 paused on 2026-10-25 20:50:30\n"),
    (None, "America/Toronto", "Task 12 in mycount is paused.\n"),
])
def test_cli_pause_over_zmq(tmp_path, monkeypatch, capsys, paused_at, zone, expected):
    repository = SimpleNamespace(identity="github.com/example/mycount", name="mycount")
    monkeypatch.setattr(cli, "LocalRepository", lambda: SimpleNamespace(repository=repository))
    config = tmp_path / "devlog.json"
    config.write_text(json.dumps({"timezone": zone}))

    @contextmanager
    def handler():
        def respond(request):
            assert request.method == "pause"
            assert request.payload == {"repository": repository.identity}
            return {"status": "ok", "result": {"task_id": 12, "status": "paused", "paused_at": paused_at}}
        yield respond

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        assert cli.main(["--config", str(config), "--server", server.endpoint, "pause"]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected
    assert captured.err == ""


def test_cli_pause_without_task_keeps_error(monkeypatch, capsys):
    repository = SimpleNamespace(identity="github.com/example/mycount", name="mycount")
    monkeypatch.setattr(cli, "LocalRepository", lambda: SimpleNamespace(repository=repository))

    @contextmanager
    def handler():
        yield lambda request: {"status": "error", "error": {
            "code": "no_task", "message_key": "error.no_task",
        }}

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        assert cli.main(["--server", server.endpoint, "pause"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "This repository has no unfinished task. Run dl start first.\n"


@pytest.mark.database
def test_real_cli_global_status(service, tasks, tmp_path):
    def status(expected):
        result = dl(tmp_path, service, "status")
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected + "\n"

    status("No task currently running")
    first = tasks.start("github.com/example/mycount")["task_id"]
    status(f"Repository (mycount): Task #{first} running for 00:00 (HH:MM)")
    second = tasks.start("github.com/example/other")["task_id"]
    status(f"Repository (other): Task #{second} running for 00:00 (HH:MM)")
    tasks.pause("github.com/example/other")
    status("No task currently running")
    tasks.start("github.com/example/mycount")
    status(f"Repository (mycount): Task #{first} running for 00:00 (HH:MM)")
    tasks.complete("github.com/example/mycount", first, "a" * 40, "done")
    status("No task currently running")


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
