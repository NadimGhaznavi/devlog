#!/usr/bin/env python3
"""Install a prepared DevLog checkout under /opt/prod/devlog."""

import argparse
import grp
import ipaddress
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.error import URLError
from urllib.request import urlopen


SOURCE = Path(__file__).resolve().parents[1]
BASE = Path("/opt/prod/devlog")
UNIT = Path("/etc/systemd/system/devlog.service")
ACCOUNT = "devlog"
MANIFEST = ".installation-manifest.json"
VERSION_MARKER = ".deployment-version"
CONSTANTS = Path("devlog/constants/DDevLog.py")
BMFORGE_COMPONENT = {"id": "bmforge.installation", "spec_version": "0.1.0"}


def reject_installed_path_symlinks():
    """Do not write through symlinked installation-owned directories."""
    for path in (BASE, BASE / "bin", BASE / "releases", BASE / "conf",
                 BASE / "devlog", BASE / "devlog/constants"):
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlinked installation path: {path}")


def package_version():
    """Check packaging against literal CMDB metadata before any host changes."""
    checker_file = SOURCE / "scripts/check-cmdb.py"
    spec = importlib.util.spec_from_file_location("devlog_cmdb_checker", checker_file)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    data = checker.validate((SOURCE / CONSTANTS).read_text(encoding="utf-8"),
                            "DevLog", CONSTANTS.as_posix())
    version = tomllib.loads((SOURCE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if version != data["VERSION"]:
        raise RuntimeError(f"Package version {version} differs from DDevLog.VERSION {data['VERSION']}")
    return version


def atomic_write(path, contents):
    """Keep each installed metadata file coherent if interrupted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".devlog-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(contents)
            os.fchmod(handle.fileno(), 0o644)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def ownership():
    """Read only this application's existing manifest; never trust arbitrary paths."""
    path = BASE / MANIFEST
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Installation ownership manifest must be a regular file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("project") != "DevLog"
            or not isinstance(data.get("releases"), list)
            or not isinstance(data.get("files"), list)):
        raise RuntimeError("Installation ownership manifest is invalid")
    for entry in data["releases"]:
        relative = Path(entry) if isinstance(entry, str) else Path("")
        if (len(relative.parts) != 2 or relative.parts[0] != "releases"
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", relative.parts[1])):
            raise RuntimeError("Unsafe managed release path")
        target = BASE / relative
        if target.is_symlink():
            raise RuntimeError("Managed release directory cannot be a symlink")
    return data


def installed_inventory(role):
    """Only the server role advertises local DBs/listeners to CMDB."""
    source = (SOURCE / CONSTANTS).read_text(encoding="utf-8")
    if role == "server":
        return source.encode("utf-8")
    lines = source.splitlines(keepends=True)
    for field in ("CMDB_DATABASES", "CMDB_NETWORK"):
        pattern = re.compile(rf"([ \t]*{field}[ \t]*=[ \t]*)\([^\r\n]*\)([ \t]*)(\r?\n?)")
        found = [(i, pattern.fullmatch(line)) for i, line in enumerate(lines)]
        matched = [(i, m) for i, m in found if m is not None]
        if len(matched) != 1:
            raise RuntimeError(f"Expected one simple, literal {field} CMDB declaration")
        index, match = matched[0]
        lines[index] = match.group(1) + "()" + match.group(2) + match.group(3)
    return "".join(lines).encode("utf-8")


def record_installation(role, version, release, previous_release, old_manifest):
    """Record the installed role, ownership and version only after activation succeeds."""
    releases = set(old_manifest.get("releases", ())) if old_manifest else set()
    for folder in (previous_release, release):
        if folder is not None:
            try:
                relative = folder.relative_to(BASE)
            except ValueError:
                continue
            if len(relative.parts) == 2 and relative.parts[0] == "releases":
                releases.add(relative.as_posix())
    files = [CONSTANTS.as_posix(), "bin/dl", "current", "conf/installation.json"]
    if role == "server":
        files.extend(("bin/dl-server", "bin/dl-db-init"))
    atomic_write(BASE / CONSTANTS, installed_inventory(role))
    atomic_write(BASE / "conf/installation.json", (json.dumps({"role": role}) + "\n").encode())
    record = {"project": "DevLog", "role": role,
              "files": files, "releases": sorted(releases)}
    if role == "server":
        record["service_unit"] = str(UNIT)
    atomic_write(BASE / MANIFEST, (json.dumps(record, indent=2) + "\n").encode())
    atomic_write(BASE / VERSION_MARKER, (version + "\n").encode())


def uninstall():
    """Remove managed binaries and service, retaining user configuration and data."""
    current = BASE / "current"
    previous = ownership()
    if not current.is_symlink():
        if previous is not None and not previous.get("removed"):
            raise RuntimeError("Installation marker is inconsistent with current release")
        print("DevLog is not installed; nothing to uninstall.")
        return
    if previous is None or previous.get("removed"):
        raise RuntimeError("Legacy installation has no ownership manifest; upgrade before uninstalling")
    role = installed_role()
    if previous.get("role") != role:
        raise RuntimeError("Installed role does not match ownership manifest")
    owned_constant = BASE / CONSTANTS
    if owned_constant.is_symlink():
        raise RuntimeError("Managed CMDB constants must not be a symlink")
    if role == "server" and (UNIT.exists() or UNIT.is_symlink()):
        if UNIT.is_symlink() or UNIT.read_bytes() != (SOURCE / "systemd/devlog.service").read_bytes():
            raise RuntimeError("Systemd unit has changed; inspect before uninstalling")
        run("systemctl", "stop", "devlog.service")
        run("systemctl", "disable", "devlog.service")
        UNIT.unlink()
        run("systemctl", "daemon-reload")
    for name in (("dl", "dl-server", "dl-db-init") if role == "server" else ("dl",)):
        target = BASE / "bin" / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            raise RuntimeError(f"Refusing to remove non-symlink launcher: {target}")
    current.unlink()
    for relative in previous["releases"]:
        target = BASE / relative
        if target.is_dir():
            shutil.rmtree(target)
    owned_constant.unlink(missing_ok=True)
    for folder in (owned_constant.parent, owned_constant.parent.parent, BASE / "bin", BASE / "releases"):
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    (BASE / "conf/installation.json").unlink(missing_ok=True)
    (BASE / VERSION_MARKER).unlink(missing_ok=True)
    # Configuration, credentials and the MariaDB database remain intact.
    atomic_write(BASE / MANIFEST, (json.dumps({
        "project": "DevLog", "files": [], "releases": [],
        "role": role, "removed": True}, indent=2) + "\n").encode())
    print(f"DevLog {role} executable installation removed; configuration and data retained.")


def server_host(value):
    """Validate an address without requiring DNS or a running server at install time."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        hostname = value.removesuffix(".")
        labels = hostname.split(".")
        if len(hostname) > 253 or re.fullmatch(r"[0-9.]+", hostname) or any(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) is None
            for label in labels
        ):
            raise argparse.ArgumentTypeError("-server must be an IPv4 address or hostname")
        return value
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise argparse.ArgumentTypeError("-server must be a connectable IPv4 address or hostname")
    return str(address)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    client = actions.add_parser("install", help="Install only the dl client")
    client.add_argument("-server", "--server", required=True, type=server_host, metavar="HOST",
                        help="DevLog server IPv4 address or hostname (ZMQ port 19701)")
    actions.add_parser("install-server", help="Install the server, database, service, and local CLI")
    actions.add_parser("upgrade", help="Upgrade this machine's installed client or server")
    actions.add_parser("uninstall", help="Remove installed client/server code, retaining configuration and data")
    for action in actions.choices.values():
        action.add_argument("--check", action="store_true", help="Validate without changing installed files")
    return parser, parser.parse_args(argv)


def installed_role():
    marker = BASE / "conf/installation.json"
    if marker.exists():
        role = json.loads(marker.read_text())["role"]
        if role not in ("client", "server"):
            raise RuntimeError("Unknown DevLog installation role")
        return role
    # Compatibility with the original server-only installer.
    if (BASE / "bin/dl-server").is_symlink() and (BASE / "conf/database.env").is_file():
        return "server"
    raise RuntimeError("Cannot determine installation role from conf/installation.json")


def run(*command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def provision():
    """New installs use local MariaDB admin socket access; upgrades never do."""
    credentials = BASE / "conf/database.env"
    if credentials.exists():
        return
    password = secrets.token_hex(32)
    sql = ("CREATE DATABASE IF NOT EXISTS `devlog` CHARACTER SET utf8mb4;\n"
           f"CREATE USER 'devlog'@'localhost' IDENTIFIED BY '{password}';\n"
           "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES "
           "ON `devlog`.* TO 'devlog'@'localhost';\n")
    run("mariadb", "--protocol=socket", "--skip-ssl", "--user=root", input=sql, text=True)
    fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(fd, "w") as stream:
        stream.write(f"DB_HOST=localhost\nDB_PORT=3306\nDB_NAME=devlog\nDB_USER=devlog\nDB_PASSWORD={password}\n")
    os.chown(credentials, 0, grp.getgrnam(ACCOUNT).gr_gid)


def select_release(release):
    candidate = BASE / ".current-new"
    if candidate.is_symlink():
        candidate.unlink()
    candidate.symlink_to(release)
    candidate.replace(BASE / "current")


def wait_ready():
    config = json.loads((BASE / "conf/devlog.json").read_text())
    binding = config["http"]
    host = "127.0.0.1" if binding["interface"] == "0.0.0.0" else binding["interface"]
    url = f"http://{host}:{binding['port']}/health"
    for _ in range(30):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200 and json.load(response)["status"] == "ok":
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError("DevLog did not become healthy; inspect journalctl -u devlog.service")


def activate(release, *, was_active, previous_release, previous_unit):
    """Select a prepared release, restoring the previous one on startup failure."""
    current = BASE / "current"
    try:
        if was_active:
            run("systemctl", "stop", "devlog.service")
        select_release(release)
        shutil.copyfile(SOURCE / "systemd/devlog.service", UNIT)
        run("systemctl", "daemon-reload")
        run("systemctl", "enable", "devlog.service")
        run("systemctl", "start", "devlog.service")
        wait_ready()
    except BaseException:
        subprocess.run(["systemctl", "stop", "devlog.service"], check=False)
        if previous_release is not None:
            select_release(previous_release)
        elif current.is_symlink():
            current.unlink()
        if previous_unit is not None:
            UNIT.write_bytes(previous_unit)
        elif UNIT.exists():
            UNIT.unlink()
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        if was_active and previous_release is not None:
            subprocess.run(["systemctl", "start", "devlog.service"], check=False)
        raise


def main(argv=None):
    parser, args = arguments(argv)
    if sys.version_info < (3, 11):
        parser.error("DevLog requires Python 3.11 or later")
    reject_installed_path_symlinks()
    current = BASE / "current"
    if args.action == "upgrade" and not current.is_symlink():
        parser.error("Run scripts/install.sh -server HOST or scripts/install-server.sh first")
    if args.action in ("install", "install-server") and (current.exists() or current.is_symlink()):
        parser.error("DevLog is already installed; use scripts/upgrade.sh")
    if current.is_symlink() and not current.resolve().is_dir() and args.action == "upgrade":
        raise RuntimeError("Installed current release is missing; inspect the installation")
    if args.action == "uninstall":
        if args.check:
            if current.is_symlink():
                previous = ownership()
                if previous is None or previous.get("removed"):
                    raise RuntimeError("Legacy installation needs upgrade before uninstall")
                role = installed_role()
                if previous.get("role") != role:
                    raise RuntimeError("Installed role does not match ownership manifest")
                if role == "server" and (UNIT.exists() or UNIT.is_symlink()):
                    if (UNIT.is_symlink() or
                            UNIT.read_bytes() != (SOURCE / "systemd/devlog.service").read_bytes()):
                        raise RuntimeError("Systemd unit has changed; inspect before uninstalling")
            print("uninstall: checks passed; no files changed.")
            return
        if os.geteuid() != 0:
            parser.error("Run this script with sudo")
        return uninstall()
    role = installed_role() if args.action == "upgrade" else ("client" if args.action == "install" else "server")
    server = role == "server"
    version = package_version()
    previous_manifest = ownership()
    if args.action in ("install", "install-server") and previous_manifest is None:
        if (BASE / CONSTANTS).exists() or (BASE / CONSTANTS).is_symlink():
            raise RuntimeError("Unowned CMDB constants exist; refusing overwrite")
    if previous_manifest and not previous_manifest.get("removed"):
        if args.action in ("install", "install-server"):
            raise RuntimeError("Active ownership manifest exists; inspect installation before reinstall")
        if previous_manifest.get("role") != role:
            raise RuntimeError("Existing manifest belongs to a different installation role")
    # Validate dependencies for this operation before touching host state.
    # Fresh server provisioning needs MariaDB only when credentials are absent;
    # upgrades and client installations never invoke the database admin CLI.
    required = ("git", "systemctl", "runuser") if server else ("git",)
    if args.action == "install-server" and not (BASE / "conf/database.env").exists():
        required += ("mariadb",)
    for command in required:
        if shutil.which(command) is None:
            parser.error(f"Required executable is missing: {command}")
    if args.check:
        if args.action == "upgrade":
            config = BASE / "conf/devlog.json"
            if not config.is_file():
                raise RuntimeError("Cannot upgrade without installed configuration")
        print(f"{args.action}: {role} version {version} checks passed; no files changed.")
        return
    if os.geteuid() != 0:
        parser.error("Run this script with sudo")
    os.umask(0o022)
    previous_release = current.resolve() if current.is_symlink() else None
    previous_unit = UNIT.read_bytes() if server and UNIT.exists() else None
    was_active = server and subprocess.run(["systemctl", "is-active", "--quiet", "devlog.service"]).returncode == 0
    if args.action == "install-server":
        if subprocess.run(["getent", "group", ACCOUNT], stdout=subprocess.DEVNULL).returncode:
            run("groupadd", "--system", ACCOUNT)
        if subprocess.run(["getent", "passwd", ACCOUNT], stdout=subprocess.DEVNULL).returncode:
            run("useradd", "--system", "--gid", ACCOUNT, "--no-create-home", "--home-dir", "/nonexistent",
                "--shell", "/usr/sbin/nologin", ACCOUNT)
    for name in ("conf", "bin", "releases"):
        (BASE / name).mkdir(parents=True, exist_ok=True)
    config = BASE / "conf/devlog.json"
    if not config.exists():
        if args.action == "upgrade":
            raise RuntimeError("Existing DevLog configuration is missing")
        shutil.copyfile(SOURCE / "conf/devlog.json", config)
    if not server:
        values = json.loads(config.read_text())
        if args.action == "install":
            values.setdefault("client", {})["host"] = args.server
            config.write_text(json.dumps(values, indent=2) + "\n")
        else:
            server_host(values["client"]["host"])
    else:
        if args.action == "install-server":
            provision()
        credentials = BASE / "conf/database.env"
        if not credentials.is_file() or credentials.is_symlink():
            raise RuntimeError("Expected a regular conf/database.env file")
        if credentials.stat().st_uid != 0 or credentials.stat().st_mode & 0o777 not in (0o600, 0o640):
            raise RuntimeError("database.env must be root-owned and mode 640 or 600")
        os.chown(credentials, 0, grp.getgrnam(ACCOUNT).gr_gid)
        credentials.chmod(0o640)
    release = BASE / "releases" / f"{version}-{time.time_ns()}"
    run(sys.executable, "-m", "venv", str(release / "venv"))
    python = release / "venv/bin/python"
    package = f"{SOURCE}[server]" if server else str(SOURCE)
    run(str(python), "-m", "pip", "install", "--disable-pip-version-check", package)
    if server:
        validation_environment = {key: value for key, value in os.environ.items()
                                  if not key.startswith(("DB_", "DEVLOG_"))}
        run("runuser", "-u", ACCOUNT, "--", str(release / "venv/bin/dl-db-init"), "--config", str(config),
            env=validation_environment)
    else:
        run(str(release / "venv/bin/dl"), "--version")
    for name in (("dl", "dl-server", "dl-db-init") if server else ("dl",)):
        link = BASE / "bin" / name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise RuntimeError(f"Refusing to replace non-symlink {link}")
        link.symlink_to(f"../current/venv/bin/{name}")
    if server:
        activate(release, was_active=was_active, previous_release=previous_release, previous_unit=previous_unit)
    else:
        select_release(release)
    record_installation(role, version, release, previous_release, previous_manifest)
    print(f"DevLog {role} {version} {args.action} complete: {BASE / 'bin/dl'}")


if __name__ == "__main__":
    main()
