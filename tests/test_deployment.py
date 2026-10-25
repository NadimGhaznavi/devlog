import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from devlog.constants.DDevLog import DDevLog


REAL_RUN = subprocess.run
CREDENTIALS = ("DB_HOST=localhost\nDB_PORT=3306\nDB_NAME=devlog\n"
               "DB_USER=devlog\nDB_PASSWORD=test-password\n")


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
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(module.os, "chown", lambda *args: None)
    return module, base, unit, commands


@pytest.fixture
def installed_server(deployment):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    (base / "bin").mkdir()
    release = base / "releases/0.1.0-1234"
    release.mkdir(parents=True)
    (base / "current").symlink_to(release)
    for name in ("dl", "dl-server", "dl-db-init"):
        (base / "bin" / name).symlink_to(f"../current/venv/bin/{name}")
    (base / "conf/devlog.json").write_text('{"custom":true}\n')
    (base / "conf/database.env").write_text(CREDENTIALS)
    (base / "conf/database.env").chmod(0o640)
    module.record_installation("server", DDevLog.VERSION, release, None, None)
    unit.write_bytes((module.SOURCE / "systemd/devlog.service").read_bytes())
    return deployment


@pytest.fixture
def simulated_server_host(deployment, monkeypatch):
    """Simulate root metadata and systemd without changing host accounts or files."""
    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=1000))
    monkeypatch.setattr(module, "wait_ready", lambda: None)
    original_stat = Path.stat

    def root_owned_credentials(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == base / "conf/database.env":
            fields = list(result)
            fields[4] = 0  # st_uid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "stat", root_owned_credentials)
    return deployment


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


@pytest.mark.parametrize("check", [True, False])
def test_server_reinstall_requires_mariadb_even_with_credentials(deployment, monkeypatch, check):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    (base / "conf/database.env").write_text(CREDENTIALS)
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.shutil, "which",
                        lambda name: None if name == "mariadb" else f"/usr/bin/{name}")
    with pytest.raises(SystemExit) as error:
        module.main(["install-server"] + (["--check"] if check else []))
    assert error.value.code == 2
    assert (base / "conf/database.env").read_text() == CREDENTIALS
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


def test_client_upgrade_then_uninstall_and_fresh_install(deployment, monkeypatch):
    import json

    module, base, unit, commands = deployment
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)
    module.main(["install", "-server", "devlog.example.net"])
    module.main(["upgrade"])
    manifest = json.loads((base / ".installation-manifest.json").read_text())
    assert len(manifest["releases"]) == 2
    assert manifest["role"] == "client"
    assert (base / ".deployment-version").read_text().strip() == DDevLog.VERSION
    commands.clear()
    module.main(["uninstall", "--check"])
    assert (base / "current").is_symlink()
    module.main(["uninstall"])
    assert not base.exists()
    assert not unit.exists()
    assert not any(c[0] in {"systemctl", "mariadb", "useradd", "groupadd"} for c in commands)
    module.main(["uninstall"])
    module.main(["install", "-server", "new.example.net"])
    assert json.loads((base / "conf/devlog.json").read_text())["client"]["host"] == "new.example.net"


def test_server_uninstall_removes_everything_except_credentials(installed_server, monkeypatch):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (base / "obsolete-release").mkdir()
    (base / "obsolete-release/data").write_text("remove")
    sql_calls, owners = [], []
    monkeypatch.setattr(module, "database_admin", lambda sql, values: sql_calls.append(sql))
    monkeypatch.setattr(module.os, "chown", lambda *args: owners.append(args))
    # The unprivileged check neither connects to MariaDB nor changes secrets.
    module.main(["uninstall", "--check"])
    assert commands == sql_calls == owners == []
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o640
    module.main(["uninstall"])
    assert not unit.exists()
    assert sorted(str(path.relative_to(base)) for path in base.rglob("*")) == ["conf", "conf/database.env"]
    assert (base / "conf/database.env").read_text() == CREDENTIALS
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o600
    assert owners == [(base / "conf/database.env", 0, 0)]
    assert sql_calls == ["DROP DATABASE IF EXISTS `devlog`;\nDROP USER IF EXISTS 'devlog'@'localhost';\n"]
    assert ("systemctl", "stop", "devlog.service") in commands
    assert ("systemctl", "disable", "devlog.service") in commands
    assert ("userdel", "devlog") in commands
    assert ("groupdel", "devlog") in commands
    previous_commands = commands[:]
    module.main(["uninstall"])
    assert commands == previous_commands
    assert len(sql_calls) == 1


@pytest.mark.parametrize("check", [True, False])
@pytest.mark.parametrize("missing", ["mariadb", "systemctl", "getent", "userdel", "groupdel"])
def test_server_uninstall_requires_tools_before_changes(installed_server, monkeypatch, missing, check):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.shutil, "which", lambda name: None if name == missing else f"/usr/bin/{name}")
    with pytest.raises(RuntimeError, match=f"Required executable is missing: {missing}"):
        module.main(["uninstall"] + (["--check"] if check else []))
    assert unit.exists() and (base / "current").is_symlink()
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o640
    assert commands == []


def test_failed_database_removal_keeps_installation_for_retry(installed_server, monkeypatch, capsys):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    previous_run = module.run

    def failing_run(*args, **kwargs):
        if args[0] == "mariadb":
            raise subprocess.CalledProcessError(1, args, stderr="private diagnostics")
        return previous_run(*args, **kwargs)

    monkeypatch.setattr(module, "run", failing_run)
    with pytest.raises(RuntimeError, match="MariaDB administration failed") as error:
        module.main(["uninstall"])
    assert "private diagnostics" not in str(error.value)
    assert "uninstalled" not in capsys.readouterr().out
    assert (base / "current").is_symlink() and unit.exists()
    assert (base / ".installation-manifest.json").exists()
    assert (base / "conf/database.env").read_text() == CREDENTIALS
    assert not any(command[0] in {"userdel", "groupdel"} for command in commands)
    monkeypatch.setattr(module, "run", previous_run)
    module.main(["uninstall"])
    assert not unit.exists()
    assert list(base.iterdir()) == [base / "conf"]


@pytest.mark.parametrize("old,new", [
    ("DB_HOST=localhost", "DB_HOST=remote.example.net"),
    ("DB_NAME=devlog", "DB_NAME=mysql"),
    ("DB_USER=devlog", "DB_USER=root"),
    ("DB_PASSWORD=test-password", "DB_PASSWORD=CHANGE_ME"),
])
def test_uninstall_rejects_unowned_database_before_changes(installed_server, monkeypatch, old, new):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (base / "conf/database.env").write_text(CREDENTIALS.replace(old, new))
    with pytest.raises(RuntimeError):
        module.main(["uninstall"])
    assert commands == []
    assert unit.exists() and (base / "current").is_symlink()


def test_uninstall_purges_data_retained_by_old_uninstaller(installed_server, monkeypatch):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    (base / "current").unlink()
    (base / "conf/installation.json").unlink()
    unit.unlink()
    manifest = base / ".installation-manifest.json"
    data = json.loads(manifest.read_text())
    data["removed"] = True
    manifest.write_text(json.dumps(data))
    module.main(["uninstall"])
    assert (base / "conf/database.env").read_text() == CREDENTIALS
    assert sorted(str(path.relative_to(base)) for path in base.rglob("*")) == ["conf", "conf/database.env"]
    assert any(command[0] == "mariadb" for command in commands)


def test_provision_reuses_credentials_without_environment_overrides(deployment, monkeypatch):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()
    credentials = base / "conf/database.env"
    saved = CREDENTIALS.replace("test-password", "quoted'\\password=$()é")
    credentials.write_text(saved)
    monkeypatch.setenv("DB_PASSWORD", "wrong")
    monkeypatch.setattr(module.secrets, "token_hex", lambda *_: pytest.fail("Credentials must be reused"))
    sql_calls = []
    monkeypatch.setattr(module, "database_admin", lambda sql, values: sql_calls.append((sql, values)))
    module.provision()
    assert credentials.read_text() == saved
    sql, values = sql_calls[0]
    assert values["DB_PASSWORD"] == "quoted'\\password=$()é"
    assert values["DB_PASSWORD"] not in sql
    assert "CREATE DATABASE IF NOT EXISTS `devlog`" in sql
    assert "CREATE USER IF NOT EXISTS 'devlog'@'localhost'" in sql


def test_failed_provision_saves_credentials_for_retry(deployment, monkeypatch):
    module, base, unit, commands = deployment
    (base / "conf").mkdir()

    def fail(sql, values):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(module, "database_admin", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        module.provision()
    saved = (base / "conf/database.env").read_bytes()
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(module, "database_admin", lambda sql, values: None)
    module.provision()
    assert (base / "conf/database.env").read_bytes() == saved


def test_uninstall_unlinks_extra_symlinks_without_removing_external_files(installed_server, monkeypatch, tmp_path):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep").write_text("keep")
    (base / "external-link").symlink_to(external, target_is_directory=True)
    module.main(["uninstall"])
    assert (external / "keep").read_text() == "keep"


def test_uninstall_refuses_symlinked_credentials(installed_server, monkeypatch, tmp_path):
    module, base, unit, commands = installed_server
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    external = tmp_path / "secret"
    external.write_text(CREDENTIALS)
    credentials = base / "conf/database.env"
    credentials.unlink()
    credentials.symlink_to(external)
    with pytest.raises(RuntimeError, match="Expected a regular"):
        module.main(["uninstall"])
    assert commands == []
    assert external.read_text() == CREDENTIALS


def test_server_install_upgrade_uninstall_and_reinstall(simulated_server_host, monkeypatch):
    module, base, unit, commands = simulated_server_host
    sql_calls = []
    monkeypatch.setattr(module, "database_admin", lambda sql, values: sql_calls.append(sql))
    module.main(["install-server"])
    credentials = (base / "conf/database.env").read_bytes()
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o640
    config = base / "conf/devlog.json"
    config.write_text(config.read_text().replace('"America/Toronto"', '"UTC"'))
    custom_config = config.read_bytes()
    module.main(["upgrade"])
    assert len(sql_calls) == 1  # Upgrades do not provision or drop databases.
    assert config.read_bytes() == custom_config
    assert (base / "conf/database.env").read_bytes() == credentials
    module.main(["uninstall"])
    assert not unit.exists()
    assert sorted(str(path.relative_to(base)) for path in base.rglob("*")) == ["conf", "conf/database.env"]
    monkeypatch.setattr(module.secrets, "token_hex", lambda *_: pytest.fail("Must reuse credentials"))
    module.main(["install-server"])
    assert (base / "conf/database.env").read_bytes() == credentials
    assert (base / "conf/database.env").stat().st_mode & 0o777 == 0o640
    assert config.read_bytes() == (module.SOURCE / "conf/devlog.json").read_bytes()
    assert (base / ".deployment-version").read_text().strip() == DDevLog.VERSION
    assert unit.exists() and (base / "current").is_symlink()
    assert len(sql_calls) == 3


@pytest.mark.database
def test_server_round_trip_with_real_mariadb(simulated_server_host, monkeypatch):
    import pymysql

    from devlog.interface.DbMgr import DbMgr
    from devlog.interface.TaskDb import TaskDb

    socket_path = os.environ.get("DEVLOG_TEST_DB_SOCKET")
    if not socket_path:
        pytest.skip("Set DEVLOG_TEST_DB_SOCKET to an explicitly disposable MariaDB instance")
    module, base, unit, commands = simulated_server_host
    admin = pymysql.connect(unix_socket=socket_path, host="localhost", user="root", autocommit=True)
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = 'devlog'")
        database_exists = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User = 'devlog' AND Host = 'localhost'")
        user_exists = cursor.fetchone()[0]
    if database_exists or user_exists:
        admin.close()
        pytest.skip("Deployment test requires unused devlog database/account on the disposable instance")
    (base / "conf").mkdir()
    credentials = base / "conf/database.env"
    password = "retained'\\password=$()é"
    saved = CREDENTIALS.replace("test-password", password) + f"DB_SOCKET={socket_path}\n"
    credentials.write_text(saved)
    credentials.chmod(0o600)
    options = dict(host="localhost", port=3306, user="devlog", password=password, database="devlog",
                   unix_socket=socket_path)
    fake_run = module.run

    def run(*args, **kwargs):
        if args[0] == "mariadb":
            return REAL_RUN(args, check=True, **kwargs)
        if args[0] == "runuser":
            with DbMgr(**options) as manager:
                TaskDb(manager).initialize()
        return fake_run(*args, **kwargs)

    monkeypatch.setattr(module, "run", run)
    try:
        module.main(["install-server"])
        with DbMgr(**options) as manager:
            TaskDb(manager).start("github.com/example/work")
            assert manager.query("SELECT COUNT(*) AS n FROM tasks")[0]["n"] == 1
        module.main(["upgrade"])
        with DbMgr(**options) as manager:
            assert manager.query("SELECT COUNT(*) AS n FROM tasks")[0]["n"] == 1
        module.main(["uninstall"])
        assert not unit.exists()
        assert credentials.read_text() == saved
        assert credentials.stat().st_mode & 0o777 == 0o600
        assert sorted(str(path.relative_to(base)) for path in base.rglob("*")) == ["conf", "conf/database.env"]
        with admin.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = 'devlog'")
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User = 'devlog' AND Host = 'localhost'")
            assert cursor.fetchone()[0] == 0
        module.main(["uninstall"])
        module.main(["install-server"])
        with DbMgr(**options) as manager:
            for table in ("repositories", "tasks", "intervals"):
                assert manager.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"] == 0
        assert credentials.read_text() == saved
        assert credentials.stat().st_mode & 0o777 == 0o640
        assert (base / ".deployment-version").read_text().strip() == DDevLog.VERSION
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP DATABASE IF EXISTS `devlog`")
            cursor.execute("DROP USER IF EXISTS 'devlog'@'localhost'")
        admin.close()


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
