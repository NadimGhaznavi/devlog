from contextlib import contextmanager
import json
from pathlib import Path
import socket
import time

import pytest
import zmq

from devlog.activity.Tracking import Tracking
from devlog.constants.DTracking import Method
from devlog.entity.TrackingError import TrackingError
from devlog.interface.Localizer import Localizer
from devlog.interface.TrackingHandler import TrackingHandler
from devlog.interface.ZMQClient import ZMQClient
from devlog.zmq.ZMQMsg import ZMQMsg
from devlog.zmq.ZMQServer import ZMQServer


@contextmanager
def echo_handler():
    yield lambda request: {"status": "ok", "result": request.payload}


def test_status_dispatch_rejects_repository_then_answers_global_query():
    class Tasks:
        def status(self):
            return {"task_id": 42, "repository": "github.com/example/mycount"}

    @contextmanager
    def handler():
        yield TrackingHandler(Tracking(Tasks()), Localizer(Path(__file__).resolve().parents[1] / "devlog/locales"))

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        client = ZMQClient(server.endpoint, timeout_ms=1000)
        with pytest.raises(TrackingError, match="invalid_request"):
            client.call(Method.STATUS, {"repository": "github.com/example/other"})
        assert client.call(Method.STATUS, {}) == {
            "task_id": 42, "repository": "github.com/example/mycount",
        }


@pytest.mark.parametrize("frames", [
    [b"not JSON"], [b"{}", b"extra"], [b"x" * 65537],
    [json.dumps(dict(protocol_version=True, sender="dl", target="devlog", method="health", payload={})).encode()],
    [ZMQMsg(sender="dl", target="wrong", method="health").to_json()],
    [b'\xff'],
    [b'{"protocol_version":1,"sender":"dl","target":"devlog","method":"health","payload":{"message":"\\ud800"}}'],
    [b'{"protocol_version":1,"sender":"\\udfff","target":"devlog","method":"health","payload":{}}'],
    [b'{"protocol_version":1,"sender":"dl","target":"devlog","method":"health","payload":{"\\ud800":"value"}}'],
    [b'[' * 1100 + b'0' + b']' * 1100],
])
def test_malformed_then_valid_request(frames):
    with ZMQServer("tcp://127.0.0.1:*", echo_handler) as server:
        with zmq.Context() as context, context.socket(zmq.REQ) as client:
            client.setsockopt(zmq.RCVTIMEO, 1000)
            client.setsockopt(zmq.LINGER, 0)
            client.connect(server.endpoint)
            client.send_multipart(frames)
            reply = ZMQMsg.from_json(client.recv())
            assert reply.payload["status"] == "error"
        assert ZMQClient(server.endpoint, timeout_ms=1000).call(Method.HEALTH, {}) == {}


def test_escaped_valid_surrogate_pair_is_accepted():
    # A paired escape represents a valid Unicode scalar value, not a lone surrogate.
    raw = (b'{"protocol_version":1,"sender":"dl","target":"devlog",'
           b'"method":"health","payload":{"label":"\\ud83d\\ude00"}}')
    with ZMQServer("tcp://127.0.0.1:*", echo_handler) as server:
        with zmq.Context() as context, context.socket(zmq.REQ) as client:
            client.setsockopt(zmq.RCVTIMEO, 1000)
            client.setsockopt(zmq.LINGER, 0)
            client.connect(server.endpoint)
            client.send(raw)
            reply = ZMQMsg.from_json(client.recv())
            assert reply.payload == {"status": "ok", "result": {"label": "😀"}}


def test_bind_failure_is_reported_synchronously():
    with ZMQServer("tcp://127.0.0.1:*", echo_handler) as first:
        with pytest.raises(RuntimeError, match="worker failed"):
            with ZMQServer(first.endpoint, echo_handler):
                pytest.fail("Conflicting listener must not be ready")


def test_handler_failure_replies_then_surfaces_to_supervisor():
    @contextmanager
    def failed_handler():
        def fail(request):
            raise RuntimeError("injected internal defect")
        yield fail

    server = ZMQServer("tcp://127.0.0.1:*", failed_handler)
    server.__enter__()
    with zmq.Context() as context, context.socket(zmq.REQ) as client:
        client.setsockopt(zmq.RCVTIMEO, 1000)
        client.setsockopt(zmq.LINGER, 0)
        client.connect(server.endpoint)
        client.send(ZMQMsg(sender="dl", target="devlog", method="health").to_json())
        assert ZMQMsg.from_json(client.recv()).payload["error"]["code"] == "service_error"
    with pytest.raises(RuntimeError, match="worker failed"):
        server.__exit__(None, None, None)


def test_timeout_then_new_call_does_not_reuse_broken_req_socket():
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    client = ZMQClient(f"tcp://127.0.0.1:{port}", timeout_ms=100)
    started = time.monotonic()
    with pytest.raises(TrackingError, match="request_timeout"):
        client.call(Method.START, {"repository": "test"})
    assert time.monotonic() - started < 2
    with ZMQServer(client.endpoint, echo_handler):
        assert client.call(Method.HEALTH, {}) == {}


def test_client_rejects_mismatched_response():
    @contextmanager
    def wrong_reply():
        yield lambda request: {"status": "error", "error": "invalid shape"}

    with ZMQServer("tcp://127.0.0.1:*", wrong_reply) as server:
        with pytest.raises(TrackingError, match="invalid_response"):
            ZMQClient(server.endpoint, timeout_ms=1000).call(Method.HEALTH, {})
