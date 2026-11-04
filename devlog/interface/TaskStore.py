"""Open a worker-owned DAL and translate known driver failures at its boundary."""

from contextlib import contextmanager
import logging

import pymysql
from pymysql.constants import CR

from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.interface.DbMgr import DbMgr
from devlog.interface.TaskDb import TaskDb


class TaskStore:
    def __init__(self, options):
        self.options = options

    @contextmanager
    def open(self):
        try:
            tasks = TaskDb(DbMgr(**self.options))
            try:
                yield tasks
            finally:
                tasks.db.close()
        except pymysql.Error as error:
            logging.exception("DevLog database operation failed")
            raise ServiceUnavailable("Application database unavailable") from error

    def ensure_connected(self, tasks):
        """Replace a lost connection before dispatch, without replaying commands."""
        try:
            tasks.db.health()
        except pymysql.OperationalError as error:
            if error.args[0] not in (CR.CR_SERVER_GONE_ERROR, CR.CR_SERVER_LOST):
                raise
            logging.info("Replacing lost DevLog worker database connection")
            previous = tasks.db
            tasks.db = DbMgr(**self.options)
            previous.close()
