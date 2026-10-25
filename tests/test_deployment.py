import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from devlog.constants.DDevLog import DDevLog


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
    assert not (base / ".deployment-version").exists()
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


@pytest.mark.parametrize("check", [True, False])
def test_fresh_server_requires_mariadb_before_host_changes(deployment, monkeypatch, capsys, check):
    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    # All the other server prerequisites exist; only MariaDB is missing.
    monkeypatch.setattr(module.shutil, "which",
                        lambda name: None if name == "mariadb" else f"/usr/bin/{name}")
    argv = ["install-server"] + (["--check"] if check else [])
    with pytest.raises(SystemExit) as error:
        module.main(argv)
    assert error.value.code == 2
    assert "mariadb" in capsys.readouterr().err
    assert list(base.iterdir()) == []
    assert not unit.exists()
    assert commands == []


def test_server_dry_run_succeeds_when_prerequisites_exist(deployment, monkeypatch):
    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")
    module.main(["install-server", "--check"])
    assert list(base.iterdir()) == []
    assert not unit.exists()
    assert commands == []


def test_server_with_existing_credentials_does_not_need_mariadb_executable(deployment, monkeypatch):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    (base / "conf/database.env").write_text("already configured")
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.shutil, "which",
                        lambda name: None if name == "mariadb" else f"/usr/bin/{name}")
    module.main(["install-server", "--check"])
    assert (base / "conf/database.env").read_text() == "already configured"
    assert commands == []
    assert not unit.exists()


def test_existing_server_upgrade_does_not_require_admin_database_client(deployment, monkeypatch):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    (base / "conf/installation.json").write_text('{"role":"server"}')
    (base / "conf/devlog.json").write_text("{}")
    release = base / "releases/0.1.0-1234"
    release.mkdir(parents=True)
    (base / "current").symlink_to(release)
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.shutil, "which",
                        lambda name: None if name == "mariadb" else f"/usr/bin/{name}")
    module.main(["upgrade", "--check"])
    assert (base / "current").is_symlink()
    assert commands == []
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


def test_check_mode_requires_no_root_and_makes_no_changes(deployment, monkeypatch):
    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", "remote.example.net", "--check"])
    assert list(base.iterdir()) == []
    assert commands == []
    assert not unit.exists()


def test_client_install_creates_bmforge_identity(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", "remote.example.net"])
    assert (base / ".deployment-version").read_text() == DDevLog.VERSION + "\n"
    installed_constants = base / "devlog/constants/DDevLog.py"
    installed_text = installed_constants.read_text()
    assert f'VERSION: Final[str] = "{DDevLog.VERSION}"' in installed_text
    assert "CMDB_DATABASES = ()" in installed_text
    assert "CMDB_NETWORK = ()" in installed_text
    assert module.installed_inventory("server") == (module.SOURCE / "devlog/constants/DDevLog.py").read_bytes()
    manifest = json.loads((base / ".installation-manifest.json").read_text())
    assert manifest["project"] == "DevLog"
    assert manifest["role"] == "client"
    assert manifest["files"] == [
        "devlog/constants/DDevLog.py", "bin/dl", "current", "conf/installation.json"
    ]
    assert len(manifest["releases"]) == 1
    assert not unit.exists()


def test_client_upgrade_retains_manifest_and_uninstall_preserves_config(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", "devlog.example.net"])
    configuration = (base / "conf/devlog.json").read_bytes()
    module.main(["upgrade"])
    manifest = json.loads((base / ".installation-manifest.json").read_text())
    assert len(manifest["releases"]) == 2
    assert manifest["role"] == "client"
    assert (base / ".deployment-version").read_text().strip() == DDevLog.VERSION
    commands.clear()
    module.main(["uninstall", "--check"])
    assert (base / "current").is_symlink()
    module.main(["uninstall"])
    assert not (base / "current").exists()
    assert not (base / "bin/dl").exists()
    assert not (base / "devlog/constants/DDevLog.py").exists()
    assert not (base / ".deployment-version").exists()
    assert (base / "conf/devlog.json").read_bytes() == configuration
    assert json.loads((base / ".installation-manifest.json").read_text())["removed"]
    assert not (base / "conf/installation.json").exists()
    assert not unit.exists()
    assert not any(c[0] in {"systemctl", "mariadb", "useradd", "groupadd"} for c in commands)
    module.main(["uninstall"])


def test_server_uninstall_only_removes_owned_service_and_code(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (base / "conf").mkdir()
    (base / "bin").mkdir()
    (base / "releases" / "0.1.0-1234").mkdir(parents=True)
    (base / "devlog/constants").mkdir(parents=True)
    (base / "devlog/constants/DDevLog.py").write_bytes(
        (module.SOURCE / "devlog/constants/DDevLog.py").read_bytes())
    (base / "current").symlink_to(base / "releases/0.1.0-1234")
    for name in ("dl", "dl-server", "dl-db-init"):
        (base / "bin" / name).symlink_to(f"../current/venv/bin/{name}")
    (base / "conf/installation.json").write_text('{"role":"server"}\n')
    (base / "conf/devlog.json").write_text('{"retained":true}\n')
    (base / "conf/database.env").write_text("secret")
    (base / ".deployment-version").write_text("0.1.0\n")
    (base / ".installation-manifest.json").write_text(json.dumps({
        "project": "DevLog", "role": "server",
        "files": ["devlog/constants/DDevLog.py", "bin/dl", "bin/dl-server",
                  "bin/dl-db-init", "current", "conf/installation.json"],
        "releases": ["releases/0.1.0-1234"], "service_unit": str(unit)
    }))
    unit.write_bytes((module.SOURCE / "systemd/devlog.service").read_bytes())
    module.main(["uninstall"])
    assert not unit.exists()
    assert not (base / ".deployment-version").exists()
    assert not (base / "current").is_symlink()
    assert not (base / "bin/dl-server").exists()
    assert not (base / "releases/0.1.0-1234").exists()
    assert (base / "conf/devlog.json").read_text() == '{"retained":true}\n'
    assert (base / "conf/database.env").read_text() == "secret"
    assert ("systemctl", "stop", "devlog.service") in commands
    assert ("systemctl", "disable", "devlog.service") in commands
    assert not any("mariadb" in c for c in commands)


def test_corrupt_manifest_release_path_refused_before_host_changes(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (base / ".installation-manifest.json").write_text(json.dumps({
        "project": "DevLog", "role": "client", "files": [],
        "releases": ["releases/../../foreign"]
    }))
    with pytest.raises(RuntimeError, match="Unsafe managed release path"):
        module.main(["install", "-server", "host.example.net"])
    assert not (base / "current").exists()
    assert not unit.exists()
    assert commands == []


def test_package_version_mismatch_blocks_check_before_changes(deployment, monkeypatch, tmp_path):
    module, base, unit, commands = deployment
    source = tmp_path / "separate-source"
    (source / "devlog/constants").mkdir(parents=True)
    (source / "scripts").mkdir()
    (source / "scripts/check-cmdb.py").write_bytes(
        (module.SOURCE / "scripts/check-cmdb.py").read_bytes())
    (source / "devlog/constants/DDevLog.py").write_bytes(
        (module.SOURCE / "devlog/constants/DDevLog.py").read_bytes())
    (source / "pyproject.toml").write_text('[project]\nname = "devlog"\nversion = "9.9.9"\n')
    monkeypatch.setattr(module, "SOURCE", source)
    with pytest.raises(RuntimeError, match="differs from DDevLog.VERSION"):
        module.main(["install", "-server", "host.example.net", "--check"])
    assert list(base.iterdir()) == []
    assert commands == []


def test_symlinked_install_directory_is_rejected_before_mutation(deployment, tmp_path):
    module, base, unit, commands = deployment
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "releases").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Refusing symlinked installation path"):
        module.main(["install", "-server", "host.example.net", "--check"])
    assert list(outside.iterdir()) == []
    assert commands == []
