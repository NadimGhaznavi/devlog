"""Resolve application configuration before constructing infrastructure."""

import ipaddress
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from devlog.constants.DDevLog import DDevLog
from devlog.constants.DNetwork import DNetwork
from devlog.constants.DTracking import DTracking


class Configuration:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("DEVLOG_CONFIG", DDevLog.CONFIG_FILE))
        explicit = path is not None or "DEVLOG_CONFIG" in os.environ
        if explicit or self.path.exists():
            values = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(values, dict) or set(values) - {"http", "zmq", "client", "timezone"}:
                raise ValueError("Invalid DevLog configuration keys")
        else:
            values = {}
        self.bindings = {}
        for name, (default_host, default_port) in DNetwork.BINDINGS.items():
            setting = values.get(name, {})
            if not isinstance(setting, dict) or set(setting) - {"interface", "port"}:
                raise ValueError(f"Invalid {name} configuration")
            host, port = setting.get("interface", default_host), setting.get("port", default_port)
            if not isinstance(host, str) or ipaddress.ip_address(host).version != 4:
                raise ValueError(f"{name} interface must be an IPv4 address")
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f"{name} port must be between 1 and 65535")
            self.bindings[name] = (host, port)
        if self.bindings["http"][1] == self.bindings["zmq"][1]:
            raise ValueError("HTTP and ZMQ require different ports")
        client = values.get("client", {})
        if not isinstance(client, dict) or set(client) - {"host", "timeout_ms"}:
            raise ValueError("Invalid client configuration")
        self.client_host = client.get("host", DNetwork.CLIENT_HOST)
        if not isinstance(self.client_host, str) or not self.client_host or any(
            c in self.client_host for c in "/: \t\n"
        ):
            raise ValueError("Client host must be an IPv4 address or hostname")
        self.timeout_ms = client.get("timeout_ms", DNetwork.TIMEOUT_MS)
        if type(self.timeout_ms) is not int or not 100 <= self.timeout_ms <= 60000:
            raise ValueError("Client timeout_ms must be between 100 and 60000")
        self.timezone = values.get("timezone", DTracking.TIMEZONE)
        self.zone = ZoneInfo(self.timezone)

    @property
    def endpoint(self):
        return os.environ.get("DEVLOG_ENDPOINT", f"tcp://{self.client_host}:{self.bindings['zmq'][1]}")

    @property
    def local_endpoint(self):
        host, port = self.bindings["zmq"]
        host = DNetwork.CLIENT_HOST if host == "0.0.0.0" else host
        return f"tcp://{host}:{port}"

    def database(self):
        path = Path(os.environ.get("DEVLOG_DATABASE_ENV", DDevLog.DATABASE_ENV))
        values = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if not sep or key not in {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_SOCKET"}:
                    raise ValueError("Invalid database environment file")
                if key in values:
                    raise ValueError("Duplicate database configuration key")
                values[key] = value
        for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_SOCKET"):
            if key in os.environ:
                values[key] = os.environ[key]
        for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            if not values.get(key) or values[key] == "CHANGE_ME":
                raise ValueError(f"Configure {key} in {path} or the environment")
        port = int(values.get("DB_PORT", "3306"))
        if not 1 <= port <= 65535:
            raise ValueError("DB_PORT must be between 1 and 65535")
        return dict(host=values["DB_HOST"], port=port, database=values["DB_NAME"],
                    user=values["DB_USER"], password=values["DB_PASSWORD"],
                    unix_socket=values.get("DB_SOCKET") or None,
                    connect_timeout=5, read_timeout=10, write_timeout=10)
