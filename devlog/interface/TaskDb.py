"""DevLog schema and atomic task transitions, through the canonical DbMgr."""

from datetime import datetime, timezone

from devlog.constants.DText import DText
from devlog.constants.DTracking import TaskStatus
from devlog.entity.TrackingError import TrackingError


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS repositories (
        repository_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        identity VARCHAR(512) COLLATE utf8mb4_bin NOT NULL UNIQUE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tasks (
        task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        repository_id BIGINT UNSIGNED NOT NULL,
        status ENUM('running', 'paused', 'completed') NOT NULL,
        started_at DATETIME(6) NOT NULL,
        completed_at DATETIME(6) NULL,
        commit_sha VARCHAR(64) CHARACTER SET ascii NULL,
        commit_message TEXT NULL,
        unfinished_repository BIGINT UNSIGNED GENERATED ALWAYS AS
            (CASE WHEN completed_at IS NULL THEN repository_id ELSE NULL END) PERSISTENT,
        UNIQUE KEY one_unfinished_per_repository (unfinished_repository),
        UNIQUE KEY repository_commit (repository_id, commit_sha),
        FOREIGN KEY (repository_id) REFERENCES repositories(repository_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS intervals (
        interval_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        task_id BIGINT UNSIGNED NOT NULL,
        started_at DATETIME(6) NOT NULL,
        ended_at DATETIME(6) NULL,
        active_guard TINYINT GENERATED ALWAYS AS
            (CASE WHEN ended_at IS NULL THEN 1 ELSE NULL END) PERSISTENT,
        UNIQUE KEY one_active_interval (active_guard),
        KEY report_dates (started_at, ended_at),
        FOREIGN KEY (task_id) REFERENCES tasks(task_id),
        CHECK (ended_at IS NULL OR ended_at >= started_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tracker_state (
        singleton_id TINYINT PRIMARY KEY CHECK (singleton_id = 1),
        active_task_id BIGINT UNSIGNED NULL,
        FOREIGN KEY (active_task_id) REFERENCES tasks(task_id)
    ) ENGINE=InnoDB""",
    "INSERT IGNORE INTO tracker_state (singleton_id) VALUES (1)",
)


class TaskDb:
    def __init__(self, db):
        self.db = db

    def initialize(self):
        # DDL is deliberately separate from runtime data transactions.
        for statement in SCHEMA:
            self.db.execute(statement)

    def health(self):
        self.db.health()
        rows = self.db.query("SELECT active_task_id FROM tracker_state WHERE singleton_id = 1")
        if len(rows) != 1:
            raise RuntimeError("DevLog schema is not initialized; run dl-db-init")
        return True

    def _lock(self):
        return self.db.query("SELECT active_task_id FROM tracker_state WHERE singleton_id = 1 FOR UPDATE")[0]["active_task_id"]

    @staticmethod
    def _now(now):
        return now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)

    def _unfinished(self, repository):
        rows = self.db.query("""
            SELECT t.task_id, t.status FROM tasks t
            JOIN repositories r ON r.repository_id = t.repository_id
            WHERE r.identity = %s AND t.completed_at IS NULL
        """, (repository,))
        if not rows:
            raise TrackingError("no_task", DText.NO_TASK)
        return rows[0]

    def _stop(self, task_id, now):
        changed = self.db.execute("UPDATE intervals SET ended_at = %s WHERE task_id = %s AND ended_at IS NULL", (now, task_id))
        if changed != 1:
            raise RuntimeError("Active task must have exactly one open interval")
        self.db.execute("UPDATE tasks SET status = %s WHERE task_id = %s", (TaskStatus.PAUSED, task_id))
        self.db.execute("UPDATE tracker_state SET active_task_id = NULL WHERE singleton_id = 1")

    def start(self, repository, *, now=None):
        with self.db.transaction():
            active = self._lock()
            now = self._now(now)
            repository_id = self.db.insert("""
                INSERT INTO repositories (identity) VALUES (%s)
                ON DUPLICATE KEY UPDATE repository_id = LAST_INSERT_ID(repository_id)
            """, (repository,))
            rows = self.db.query("SELECT task_id FROM tasks WHERE repository_id = %s AND completed_at IS NULL", (repository_id,))
            task_id = rows[0]["task_id"] if rows else None
            if task_id is not None and task_id == active:
                return {"task_id": task_id, "status": TaskStatus.RUNNING}
            if active is not None:
                self._stop(active, now)
            if task_id is None:
                task_id = self.db.insert("INSERT INTO tasks (repository_id, status, started_at) VALUES (%s, %s, %s)",
                                         (repository_id, TaskStatus.RUNNING, now))
            else:
                self.db.execute("UPDATE tasks SET status = %s WHERE task_id = %s", (TaskStatus.RUNNING, task_id))
            self.db.insert("INSERT INTO intervals (task_id, started_at) VALUES (%s, %s)", (task_id, now))
            self.db.execute("UPDATE tracker_state SET active_task_id = %s WHERE singleton_id = 1", (task_id,))
            return {"task_id": task_id, "status": TaskStatus.RUNNING}

    def pause(self, repository, *, now=None):
        with self.db.transaction():
            active = self._lock()
            task = self._unfinished(repository)
            if task["task_id"] == active:
                self._stop(active, self._now(now))
            return {"task_id": task["task_id"], "status": TaskStatus.PAUSED}

    def prepare_commit(self, repository, *, commit_sha=None):
        with self.db.transaction(read_only=True):
            if commit_sha:
                rows = self.db.query("""
                    SELECT t.task_id, t.status FROM tasks t JOIN repositories r
                    ON r.repository_id = t.repository_id WHERE r.identity = %s AND t.commit_sha = %s
                """, (repository, commit_sha))
                if rows:
                    return rows[0]
            return self._unfinished(repository)

    def complete(self, repository, task_id, commit_sha, message, *, now=None):
        with self.db.transaction():
            active = self._lock()
            now = self._now(now)
            rows = self.db.query("""
                SELECT t.status, t.commit_sha FROM tasks t JOIN repositories r
                ON r.repository_id = t.repository_id WHERE t.task_id = %s AND r.identity = %s
            """, (task_id, repository))
            if not rows or (rows[0]["status"] == TaskStatus.COMPLETED and rows[0]["commit_sha"] != commit_sha):
                raise TrackingError("task_conflict", DText.TASK_CONFLICT)
            if rows[0]["status"] != TaskStatus.COMPLETED:
                if active == task_id:
                    self._stop(task_id, now)
                self.db.execute("""
                    UPDATE tasks SET status = %s, completed_at = %s, commit_sha = %s, commit_message = %s
                    WHERE task_id = %s
                """, (TaskStatus.COMPLETED, now, commit_sha, message, task_id))
            return {"task_id": task_id, "status": TaskStatus.COMPLETED, "commit_sha": commit_sha}

    def repositories(self):
        return [row["identity"] for row in self.db.query("SELECT identity FROM repositories ORDER BY identity")]

    def daily_totals(self, days, repository, now):
        """Sum interval overlaps; caller supplies explicit UTC local-day boundaries."""
        day_table = " UNION ALL ".join("SELECT %s AS day, %s AS day_start, %s AS day_end" for _ in days)
        params = tuple(value for day in days for value in day)
        condition = " AND t.repository_id = (SELECT repository_id FROM repositories WHERE identity = %s)" if repository else ""
        rows = self.db.query(f"""
            SELECT d.day, COALESCE(SUM(TIMESTAMPDIFF(MICROSECOND,
                GREATEST(i.started_at, d.day_start),
                LEAST(COALESCE(i.ended_at, %s), d.day_end))), 0) / 1000000 AS seconds
            FROM ({day_table}) d
            LEFT JOIN intervals i ON i.started_at < d.day_end AND COALESCE(i.ended_at, %s) > d.day_start
                AND EXISTS (SELECT 1 FROM tasks t WHERE t.task_id = i.task_id {condition})
            GROUP BY d.day ORDER BY d.day
        """, (now, *params, now, *((repository,) if repository else ())))
        return [{"date": row["day"], "hours": float(row["seconds"]) / 3600} for row in rows]
