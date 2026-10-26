"""Compose service-owned resources; database connections stay in their worker."""

from contextlib import contextmanager
import logging
from pathlib import Path

from devlog.activity.Report import Report
from devlog.activity.TaskHistory import TaskHistory
from devlog.activity.Tracking import Tracking
from devlog.constants.DTracking import DTracking, Method
from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.entity.TrackingError import TrackingError
from devlog.interface.Localizer import Localizer
from devlog.interface.TaskStore import TaskStore
from devlog.interface.TrackingHandler import TrackingHandler
from devlog.interface.ZMQClient import ZMQClient


class Application:
    def __init__(self, config):
        self.config = config
        self.store = TaskStore(config.database())
        self.localizer = Localizer(Path(__file__).parents[1] / "locales")
        self.worker = None

    def tasks(self):
        return self.store.open()

    @contextmanager
    def handler(self):
        with self.tasks() as tasks:
            tasks.health()
            yield TrackingHandler(Tracking(tasks), self.localizer)

    def report(self, **filters):
        with self.tasks() as tasks:
            report = Report(tasks, self.config.zone).read(**filters)
            report[DTracking.CURRENT_TASK] = tasks.status()
            return report

    def task_list(self, **filters):
        with self.tasks() as tasks:
            return TaskHistory(tasks, self.config.zone).list(**filters)

    def task_detail(self, task_id):
        with self.tasks() as tasks:
            return TaskHistory(tasks, self.config.zone).read(task_id, include_editor=True)

    def save_timing(self, task_id, payload):
        with self.tasks() as tasks:
            TaskHistory(tasks, self.config.zone).save_timing(task_id, payload)

    def insert_pause(self, task_id, payload):
        with self.tasks() as tasks:
            TaskHistory(tasks, self.config.zone).insert_pause(task_id, payload)

    def health(self):
        components = {"http": "ok", "zmq": "ok", "db-server": "ok"}
        try:
            self.worker.check()
            ZMQClient(self.config.local_endpoint, timeout_ms=self.config.timeout_ms).call(Method.HEALTH, {})
        except (RuntimeError, OSError, ValueError, TrackingError):
            logging.exception("DevLog ZMQ health failed")
            components["zmq"] = "error"
        try:
            with self.tasks() as tasks:
                tasks.health()
        except (ServiceUnavailable, RuntimeError):
            logging.exception("DevLog database health failed")
            components["db-server"] = "error"
        status = "ok" if all(value == "ok" for value in components.values()) else "error"
        return {"status": status, "components": components}
