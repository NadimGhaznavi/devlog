"""Socket-owning REQ/REP worker, adapted from the pinned BMForge reference."""

from collections.abc import Callable
from threading import Event, Thread

import zmq

from devlog.constants.DNetwork import DNetwork
from devlog.constants.DTracking import DTracking
from devlog.zmq.ZMQMsg import ZMQMsg


BMFORGE_COMPONENT = {"id": "bmforge.zmq-server", "spec_version": "0.3.0"}


class ZMQServer:
    def __init__(self, endpoint: str, handler_factory: Callable, *, timeout_ms=DNetwork.TIMEOUT_MS):
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self._handler_factory = handler_factory
        self._ready, self._stop = Event(), Event()
        self._error = None
        self._thread = Thread(target=self._serve, name="devlog-zmq", daemon=True)

    def __enter__(self):
        self._thread.start()
        if not self._ready.wait(DNetwork.STARTUP_SECONDS):
            self._stop.set()
            self._thread.join(DNetwork.SHUTDOWN_SECONDS)
            raise TimeoutError("DevLog ZMQ startup timed out")
        self.check()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(DNetwork.SHUTDOWN_SECONDS)
        if self._thread.is_alive():
            raise TimeoutError("DevLog ZMQ shutdown timed out")
        self.check()

    def check(self):
        if self._error is not None:
            raise RuntimeError("DevLog ZMQ worker failed") from self._error

    def _serve(self):
        try:
            with self._handler_factory() as handler, zmq.Context() as context:
                with context.socket(zmq.REP) as socket:
                    socket.setsockopt(zmq.LINGER, 0)
                    socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
                    socket.bind(self.endpoint)
                    self.endpoint = socket.getsockopt_string(zmq.LAST_ENDPOINT)
                    self._ready.set()
                    while not self._stop.is_set():
                        if not socket.poll(DNetwork.POLL_MS):
                            continue
                        frames = socket.recv_multipart()
                        request, fatal = None, None
                        try:
                            if len(frames) != 1 or len(frames[0]) > DNetwork.MAX_MESSAGE_BYTES:
                                raise ValueError("Expected one bounded JSON frame")
                            request = ZMQMsg.from_json(frames[0])
                            if request.target != DTracking.SERVER:
                                raise ValueError("Wrong message target")
                        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                            payload = {"status": "error", "error": {
                                "code": "invalid_request", "message": "Invalid request envelope.",
                                "message_key": "error.invalid_request",
                            }}
                        else:
                            try:
                                payload = handler(request)
                            except Exception as error:
                                # Reply with an honest failure, then surface the defect to systemd.
                                fatal = error
                                payload = {"status": "error", "error": {
                                    "code": "service_error", "message": "Operation failed; inspect the service log.",
                                    "message_key": "error.unavailable",
                                }}
                        reply = ZMQMsg(sender=DTracking.SERVER,
                                       target=request.sender if request else None,
                                       method=request.method if request else "error", payload=payload)
                        socket.send(reply.to_json())
                        if fatal is not None:
                            raise fatal
        except BaseException as error:
            self._error = error
        finally:
            self._ready.set()
