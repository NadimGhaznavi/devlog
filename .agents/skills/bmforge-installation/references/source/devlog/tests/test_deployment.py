import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("devlog_deploy", Path(__file__).parents[1] / "scripts/deploy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = tmp_path / "production"
    base.mkdir()
    unit = tmp_path / "devlog.service"
    monkeypatch.setattr(module, "BASE", base)
    monkeypatch.setattr(module, "UNIT", unit)
    commands = []

    def run(*args, **kwargs):
        commands.append(tuple(args[0]) if len(args) == 1 and isinstance(args[0], list) else args)
        if len(args) >= 4 and args[1:3] == ("-m", "venv"):
            (Path(args[3]) / "bin").mkdir(parents=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(module.subprocess, "run", run)
    return module, base, unit, commands


def test_failed_upgrade_restores_previous_release_and_unit(deployment, monkeypatch):
    module, base, unit, commands = deployment
    old, new = base / "old", base / "new"
    old.mkdir()
    new.mkdir()
    (base / "current").symlink_to(old)
    unit.write_bytes(b"previous unit")

    def unhealthy():
        assert (base / "current").resolve() == new
        raise RuntimeError("startup failed")

    monkeypatch.setattr(module, "wait_ready", unhealthy)
    with pytest.raises(RuntimeError, match="startup failed"):
        module.activate(new, was_active=True, previous_release=old, previous_unit=b"previous unit")
    assert (base / "current").resolve() == old
    assert unit.read_bytes() == b"previous unit"
    assert commands[-1] == ("systemctl", "start", "devlog.service")
    assert not any("mariadb" in command for command in commands)


def test_successful_activation_preserves_configuration(deployment, monkeypatch):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    config = base / "conf/devlog.json"
    config.write_text('{"custom":"preserved"}')
    release = base / "new"
    release.mkdir()
    monkeypatch.setattr(module, "wait_ready", lambda: None)
    module.activate(release, was_active=False, previous_release=None, previous_unit=None)
    assert (base / "current").resolve() == release
    assert config.read_text() == '{"custom":"preserved"}'
    assert unit.read_bytes() == (module.SOURCE / "systemd/devlog.service").read_bytes()


def test_client_install_requires_server_before_any_changes(deployment):
    module, base, unit, commands = deployment
    with pytest.raises(SystemExit) as error:
        module.main(["install"])
    assert error.value.code == 2
    assert list(base.iterdir()) == []
    assert commands == []


@pytest.mark.parametrize("host", ["192.168.1.20", "devlog.example.net", "devlog-box", "localhost"])
def test_client_install_saves_host_without_server_side_effects(deployment, monkeypatch, host):
    import json

    from devlog.interface.Configuration import Configuration

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    # A client machine has no server executables installed.
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", host])
    config = Configuration(base / "conf/devlog.json")
    assert config.endpoint == f"tcp://{host}:19701"
    assert json.loads((base / "conf/installation.json").read_text()) == {"role": "client"}
    assert (base / "bin/dl").is_symlink()
    assert not (base / "bin/dl-server").exists()
    assert not (base / "conf/database.env").exists()
    assert not unit.exists()
    assert all(command[0] not in {"systemctl", "mariadb", "useradd", "groupadd", "runuser"} for command in commands)
    installs = [command for command in commands if "pip" in command]
    assert len(installs) == 1 and installs[0][-1] == str(module.SOURCE)


@pytest.mark.parametrize("host", ["", "https://host", "host:19701", "bad host", "-bad", "999.1.1.1", "0.0.0.0"])
def test_invalid_server_rejected_before_installation(deployment, host):
    module, base, unit, commands = deployment
    with pytest.raises(SystemExit) as error:
        module.main(["install", "-server", host])
    assert error.value.code == 2
    assert list(base.iterdir()) == []
    assert commands == []


def test_client_upgrade_preserves_host_and_role(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", "remote.example.net"])
    config = (base / "conf/devlog.json").read_bytes()
    previous = (base / "current").resolve()
    commands.clear()
    module.main(["upgrade"])
    assert (base / "current").resolve() != previous
    assert (base / "conf/devlog.json").read_bytes() == config
    assert json.loads((base / "conf/installation.json").read_text())["role"] == "client"
    assert all(command[0] not in {"systemctl", "mariadb", "useradd", "groupadd", "runuser"} for command in commands)
    assert not unit.exists()


def test_server_install_has_no_client_host_requirement(deployment):
    module, *_ = deployment
    _, arguments = module.arguments(["install-server"])
    assert arguments.action == "install-server"


def test_original_server_installation_is_recognized(deployment):
    module, base, *_ = deployment
    (base / "bin").mkdir()
    (base / "conf").mkdir()
    (base / "bin/dl-server").symlink_to("../current/venv/bin/dl-server")
    (base / "conf/database.env").write_text("existing credentials")
    assert module.installed_role() == "server"
