from typing import Final


class DDevLog:
    VERSION: Final[str] = "0.10.3"
    NAME: Final[str] = "devlog"
    SERVICE_USER: Final[str] = "devlog"
    BASE_DIR: Final[str] = "/opt/prod/devlog"
    CONFIG_FILE: Final[str] = "/opt/prod/devlog/conf/devlog.json"
    DATABASE_ENV: Final[str] = "/opt/prod/devlog/conf/database.env"
    CMDB_TYPE: Final[str] = "application"
    CMDB_SUBTYPE: Final[str] = "time-tracker"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Polonium"
    CMDB_COMPONENTS = (("Configuration", "/opt/prod/devlog/conf"),)
    CMDB_DATABASES = (("DevLog", "devlog"),)
    CMDB_NETWORK = (("http", "0.0.0.0", 19700), ("zmq", "0.0.0.0", 19701))
