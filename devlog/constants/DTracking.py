from enum import StrEnum
from typing import Final


class TaskStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class Method(StrEnum):
    STATUS = "status"
    START = "start"
    PAUSE = "pause"
    COMMIT = "commit"
    RELEASE = "release"
    HEALTH = "health"


class HistoryKind(StrEnum):
    TASK = "task"
    RELEASE = "release"


class DTracking:
    ENTRIES: Final[str] = "entries"
    ENTRY_TYPE: Final[str] = "entry_type"
    PROTOCOL_VERSION: Final[int] = 1
    SERVER: Final[str] = "devlog"
    CLIENT: Final[str] = "dl"
    REPOSITORY: Final[str] = "repository"
    TASK_ID: Final[str] = "task_id"
    ACTIVE_SECONDS: Final[str] = "active_seconds"
    CURRENT_TASK: Final[str] = "current_task"
    PAUSED_AT: Final[str] = "paused_at"
    COMMIT_SHA: Final[str] = "commit_sha"
    MESSAGE: Final[str] = "message"
    PHASE: Final[str] = "phase"
    PREPARE: Final[str] = "prepare"
    COMPLETE: Final[str] = "complete"
    TIMEZONE: Final[str] = "America/Toronto"
    HISTORY_TIME_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
    TASK_DATE_FORMAT: Final[str] = "%d %b %Y"
    REPORT_DAYS: Final[int] = 7
    MAX_REPORT_DAYS: Final[int] = 366
    PROJECT_COLORS: Final[tuple[str, ...]] = (
        "#FF6B6B", "#35CDE0", "#F4D35E", "#AD8CFF",
        "#4DCEA0", "#F49A52", "#6E9EF5", "#EF83C5",
        "#A6CD55", "#8CDBF2", "#C69BCB", "#DDBF8C",
        "#44A99B", "#EAE3B2", "#CC826D", "#A7B7D1",
        "#D8DF8A", "#F5AC9E", "#A5D6BB", "#CBC2F5",
    )
    # Plotly shapes, also used by the daily table's CSS swatches. Similar hues
    # in later palette groups get another visual cue, independent of filters.
    PROJECT_PATTERNS: Final[tuple[str, ...]] = (
        "", "", "", "", "", "", "", "",
        "/", "/", "/", "/", "/", "/", "/", "/",
        ".", ".", ".", ".",
    )
    TASK_HOURS: Final[str] = "task_hours"
    MAX_REPOSITORY: Final[int] = 512
    MAX_COMMIT_MESSAGE: Final[int] = 16384
    INTERVAL_ID: Final[str] = "interval_id"
    PAUSE_START: Final[str] = "pause_start"
    PAUSE_END: Final[str] = "pause_end"
    REVISION: Final[str] = "revision"
    INTERVALS: Final[str] = "intervals"
    STARTED_AT: Final[str] = "started_at"
    ENDED_AT: Final[str] = "ended_at"
    LOADED_AT: Final[str] = "loaded_at"
    RANGE_START: Final[str] = "range_start"
    TIMING_CONTEXT_SECONDS: Final[int] = 3600
    MAX_TIMING_INTERVALS: Final[int] = 1024
    MIN_TIMING_YEAR: Final[int] = 1000
