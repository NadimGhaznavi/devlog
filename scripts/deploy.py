#!/usr/bin/env python3
"""Install a prepared DevLog checkout under /opt/prod/devlog."""

import argparse
import grp
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import tomllib
from urllib.error import URLError
from urllib.request import urlopen


SOURCE = Path(__file__).resolve().parents[1]
BASE = Path("/opt/prod/devlog")
UNIT = Path("/etc/systemd/system/devlog.service")
ACCOUNT = "devlog"


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
    if os.geteuid() != 0:
        parser.error("Run this script with sudo")
    os.umask(0o022)
    if sys.version_info < (3, 11):
        parser.error("DevLog requires Python 3.11 or later")
    current = BASE / "current"
    if args.action == "upgrade" and not current.is_symlink():
        parser.error("Run scripts/install.sh -server HOST or scripts/install-server.sh first")
    if args.action != "upgrade" and current.exists():
        parser.error("DevLog is already installed; use scripts/upgrade.sh")
    role = installed_role() if args.action == "upgrade" else ("client" if args.action == "install" else "server")
    server = role == "server"
    for command in (("git", "systemctl", "runuser") if server else ("git",)):
        if shutil.which(command) is None:
            parser.error(f"Required executable is missing: {command}")
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
    version = tomllib.loads((SOURCE / "pyproject.toml").read_text())["project"]["version"]
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
    marker = BASE / "conf/.installation.json.new"
    marker.write_text(json.dumps({"role": role}) + "\n")
    marker.replace(BASE / "conf/installation.json")
    print(f"DevLog {role} {version} {args.action} complete: {BASE / 'bin/dl'}")


if __name__ == "__main__":
    main()
