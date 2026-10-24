from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pymysql
import pytest

from devlog.interface.DbMgr import DbMgr
from devlog.interface.TaskDb import TaskDb


ROOT = Path(__file__).resolve().parents[1]


def git(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True)


@pytest.fixture
def checkout(tmp_path):
    remote, root = tmp_path / "remote.git", tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "DevLog Test")
    git(root, "config", "user.email", "devlog@example.invalid")
    (root / "initial").write_text("initial\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initial")
    git(root, "remote", "add", "origin", "git@github.com:Example/Project.git")
    git(root, "remote", "set-url", "--push", "origin", str(remote))
    git(root, "push", "--set-upstream", "origin", "main")
    return root, remote


@pytest.fixture
def db_options():
    socket_path = os.environ.get("DEVLOG_TEST_DB_SOCKET")
    if not socket_path:
        pytest.skip("Set DEVLOG_TEST_DB_SOCKET to an explicitly disposable MariaDB instance")
    name = "dl_test_" + secrets.token_hex(6)
    password = secrets.token_hex(20)
    admin = pymysql.connect(unix_socket=socket_path, host="localhost",
                            user=os.environ.get("DEVLOG_TEST_DB_USER", "root"),
                            password=os.environ.get("DEVLOG_TEST_DB_PASSWORD", ""), autocommit=True)
    try:
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
            cursor.execute(f"CREATE USER '{name}'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute(f"GRANT ALL ON `{name}`.* TO '{name}'@'localhost'")
        options = dict(host="localhost", port=3306, user=name, password=password, database=name,
                       unix_socket=socket_path, connect_timeout=2, read_timeout=2, write_timeout=2)
        with DbMgr(**options) as manager:
            TaskDb(manager).initialize()
        yield options
    finally:
        with admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
            cursor.execute(f"DROP USER IF EXISTS '{name}'@'localhost'")
        admin.close()


@pytest.fixture
def tasks(db_options):
    with DbMgr(**db_options) as db:
        yield TaskDb(db)


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@pytest.fixture
def service(tmp_path, db_options):
    http, zmq = free_port(), free_port()
    config = tmp_path / "devlog.json"
    config.write_text(json.dumps(dict(http=dict(interface="127.0.0.1", port=http),
                                     zmq=dict(interface="127.0.0.1", port=zmq),
                                     client=dict(timeout_ms=1000), timezone="America/Toronto")))
    environment = {**os.environ, "DEVLOG_CONFIG": str(config), "DB_HOST": "localhost", "DB_PORT": "3306",
                   "DB_NAME": db_options["database"], "DB_USER": db_options["user"],
                   "DB_PASSWORD": db_options["password"], "DB_SOCKET": db_options["unix_socket"],
                   "PYTHONPATH": str(ROOT)}
    logfile = tmp_path / "server.log"
    processes = []

    def start():
        with logfile.open("a") as stream:
            process = subprocess.Popen([sys.executable, "-m", "devlog.server.main", "--config", str(config)],
                                       env=environment, cwd=tmp_path, stdout=stream, stderr=stream)
        processes.append(process)
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail(logfile.read_text())
            try:
                with urlopen(f"http://127.0.0.1:{http}/health", timeout=.5) as response:
                    if response.status == 200:
                        return process
            except (URLError, OSError):
                time.sleep(.05)
        pytest.fail("Service did not start: " + logfile.read_text())

    process = start()
    try:
        yield dict(process=process, start=start, endpoint=f"tcp://127.0.0.1:{zmq}",
                   url=f"http://127.0.0.1:{http}", environment=environment, logfile=logfile)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)


def dl(root, service, *arguments):
    return subprocess.run([sys.executable, "-m", "devlog.cli", *arguments], cwd=root,
                          env=service["environment"], capture_output=True, text=True, timeout=15)
