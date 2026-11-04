from types import SimpleNamespace
from unittest.mock import Mock

import pymysql
from pymysql.constants import CR
import pytest

from devlog.activity.Application import Application
from devlog.constants.DTracking import Method
from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.interface.TaskDb import TaskDb
from devlog.zmq.ZMQMsg import ZMQMsg


@pytest.fixture
def worker(monkeypatch):
    managers = [Mock(), Mock()]
    for manager in managers:
        manager.query.return_value = [{"active_task_id": None}]
    connect = Mock(side_effect=managers)
    monkeypatch.setattr("devlog.interface.TaskStore.DbMgr", connect)
    status = Mock(return_value={"task_id": None})
    monkeypatch.setattr(TaskDb, "status", status)
    app = Application(SimpleNamespace(database=lambda: {}))
    return app, connect, managers, status


def request(method=Method.STATUS):
    return ZMQMsg(sender="dl", target="devlog", method=method, payload={})


def test_healthy_worker_checks_and_reuses_connection(worker):
    app, connect, (first, unused), status = worker
    with app.handler() as handle:
        for _ in range(2):
            assert handle(request()) == {"status": "ok", "result": {"task_id": None}}
        assert first.health.call_count == 3  # Startup and both commands.
        first.close.assert_not_called()
    connect.assert_called_once_with()
    first.close.assert_called_once_with()
    unused.close.assert_not_called()
    assert status.call_count == 2


@pytest.mark.parametrize("code", [CR.CR_SERVER_GONE_ERROR, CR.CR_SERVER_LOST])
def test_lost_connection_is_replaced_before_command_and_then_reused(worker, code):
    app, connect, (first, replacement), status = worker
    with app.handler() as handle:
        first.health.side_effect = pymysql.OperationalError(code, "connection lost")
        assert handle(request())["status"] == "ok"
        first.close.assert_called_once_with()
        replacement.close.assert_not_called()
        assert handle(request())["status"] == "ok"
    assert connect.call_count == 2
    first.close.assert_called_once_with()
    replacement.close.assert_called_once_with()
    replacement.health.assert_called_once_with()
    assert status.call_count == 2


def test_reconnect_failure_is_not_retried_and_command_does_not_run(worker):
    app, connect, (first, unused), status = worker
    failure = pymysql.OperationalError(CR.CR_CONN_HOST_ERROR, "connection refused")
    with pytest.raises(ServiceUnavailable) as error:
        with app.handler() as handle:
            first.health.side_effect = pymysql.OperationalError(CR.CR_SERVER_LOST, "connection lost")
            connect.side_effect = failure
            handle(request())
    assert error.value.__cause__ is failure
    assert connect.call_count == 2
    status.assert_not_called()
    first.close.assert_called_once_with()
    unused.close.assert_not_called()


@pytest.mark.parametrize("failure", [
    pymysql.OperationalError(1045, "access denied"),
    pymysql.ProgrammingError(1146, "missing table"),
])
def test_other_database_errors_do_not_trigger_reconnection(worker, failure):
    app, connect, (first, unused), status = worker
    with pytest.raises(ServiceUnavailable) as error:
        with app.handler() as handle:
            first.health.side_effect = failure
            handle(request())
    assert error.value.__cause__ is failure
    connect.assert_called_once_with()
    status.assert_not_called()
    first.close.assert_called_once_with()


def test_failed_write_is_never_replayed(worker, monkeypatch):
    app, connect, (first, unused), status = worker
    failure = pymysql.OperationalError(CR.CR_SERVER_LOST, "connection lost during command")
    start = Mock(side_effect=failure)
    monkeypatch.setattr(TaskDb, "start", start)
    with pytest.raises(ServiceUnavailable) as error:
        with app.handler() as handle:
            handle(ZMQMsg(sender="dl", target="devlog", method=Method.START,
                          payload={"repository": "github.com/example/project"}))
    assert error.value.__cause__ is failure
    start.assert_called_once_with("github.com/example/project")
    connect.assert_called_once_with()
    first.close.assert_called_once_with()


def test_native_health_reports_lost_connection_without_reconnecting(worker):
    app, connect, (first, unused), status = worker
    with pytest.raises(ServiceUnavailable):
        with app.handler() as handle:
            first.health.side_effect = pymysql.OperationalError(CR.CR_SERVER_LOST, "connection lost")
            handle(request(Method.HEALTH))
    connect.assert_called_once_with()
    first.close.assert_called_once_with()
