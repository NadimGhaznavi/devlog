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
    HEALTH = "health"


class DTracking:
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
    TASK_TOTAL_SECONDS_LIMIT: Final[int] = 5 * 60
    REPORT_DAYS: Final[int] = 7
    MAX_REPORT_DAYS: Final[int] = 366
    PROJECT_COLORS: Final[tuple[str, ...]] = (
        "#E63946", "#00BCD4", "#FFD60A", "#7C3AED",
        "#22C55E", "#F77F00", "#2563EB", "#EC4899",
        "#7AC800", "#009DFF", "#BE185D", "#FFA600",
        "#00A896", "#A855F7", "#F35425", "#4F46E5",
        "#BAD80A", "#F43F5E", "#00B894", "#D946EF",
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
