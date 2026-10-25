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
    REPORT_DAYS: Final[int] = 7
    MAX_REPORT_DAYS: Final[int] = 366
    TASK_HOURS: Final[str] = "task_hours"
    MAX_REPOSITORY: Final[int] = 512
    MAX_COMMIT_MESSAGE: Final[int] = 16384
    INTERVAL_ID: Final[str] = "interval_id"
    PAUSE_START: Final[str] = "pause_start"
    PAUSE_END: Final[str] = "pause_end"
