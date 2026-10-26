from typing import Final

from devlog.constants.DDevLog import DDevLog


class DNetwork:
    BINDINGS: Final = {name: (host, port) for name, host, port in DDevLog.CMDB_NETWORK}
    CLIENT_HOST: Final[str] = "127.0.0.1"
    TIMEOUT_MS: Final[int] = 5000
    POLL_MS: Final[int] = 100
    STARTUP_SECONDS: Final[int] = 15
    SHUTDOWN_SECONDS: Final[int] = 35
    HTTP_TIMEOUT: Final[int] = 10
    MAX_MESSAGE_BYTES: Final[int] = 65536
    MAX_QUERY_FIELDS: Final[int] = 10
    MAX_FORM_BYTES: Final[int] = 8192
    MAX_TIMING_BYTES: Final[int] = 262144
