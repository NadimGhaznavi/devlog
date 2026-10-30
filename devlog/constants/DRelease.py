from typing import Final


class DRelease:
    TAG_NAME: Final[str] = "tag_name"
    CODENAME: Final[str] = "codename"
    RELEASED_AT: Final[str] = "released_at"
    RELEASE_ID: Final[str] = "release_id"
    RELEASES: Final[str] = "releases"
    INSERTED: Final[str] = "inserted"
    TAG_PATTERN: Final[str] = r"v?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
    MAX_TAG_BYTES: Final[int] = 255
    MAX_CODENAME_BYTES: Final[int] = 1024
