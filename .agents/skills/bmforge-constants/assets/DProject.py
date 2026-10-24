from typing import Final


class DProject:
    VERSION: Final[str] = "0.0.0"
    CMDB_TYPE: Final[str] = "application"
    CMDB_SUBTYPE: Final[str] = "__PROJECT_SUBTYPE__"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Initial development"
    CMDB_COMPONENTS = ()
    CMDB_DATABASES = ()
    # Declare every owned listener; runtime defaults must use these bindings.
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = ()
    BASE_DIR: Final[str] = "/opt/prod/__PROJECT_SLUG__"
