"""Open a worker-owned DAL and translate known driver failures at its boundary."""

from contextlib import contextmanager
import logging

import pymysql

from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.interface.DbMgr import DbMgr
from devlog.interface.TaskDb import TaskDb


class TaskStore:
    def __init__(self, options):
        self.options = options

    @contextmanager
    def open(self):
        try:
            with DbMgr(**self.options) as manager:
                yield TaskDb(manager)
        except pymysql.Error as error:
            logging.exception("DevLog database operation failed")
            raise ServiceUnavailable("Application database unavailable") from error
