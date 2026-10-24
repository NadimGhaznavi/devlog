"""Bounded calls with fresh REQ sockets and no automatic mutation retries."""

import zmq

from devlog.constants.DNetwork import DNetwork
from devlog.constants.DText import DText
from devlog.constants.DTracking import DTracking
from devlog.entity.TrackingError import TrackingError
from devlog.zmq.ZMQMsg import ZMQMsg


class ZMQClient:
    def __init__(self, endpoint, *, timeout_ms=DNetwork.TIMEOUT_MS):
        if not isinstance(endpoint, str) or not endpoint.startswith("tcp://"):
            raise TrackingError("invalid_endpoint", DText.INVALID_ENDPOINT)
        host, separator, port = endpoint.removeprefix("tcp://").rpartition(":")
        if not separator or not host or any(c in host for c in "/:@? \t\n") or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise TrackingError("invalid_endpoint", DText.INVALID_ENDPOINT)
        self.endpoint, self.timeout_ms = endpoint, timeout_ms

    def call(self, method, payload):
        request = ZMQMsg(sender=DTracking.CLIENT, target=DTracking.SERVER, method=method, payload=payload)
        try:
            with zmq.Context() as context:
                with context.socket(zmq.REQ) as socket:
                    socket.setsockopt(zmq.LINGER, 0)
                    socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
                    socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
                    socket.connect(self.endpoint)
                    socket.send(request.to_json())
                    frames = socket.recv_multipart()
        except zmq.Again as error:
            raise TrackingError("request_timeout", DText.REQUEST_TIMEOUT) from error
        except zmq.ZMQError as error:
            raise TrackingError("transport_failed", DText.TRANSPORT_FAILED) from error
        if len(frames) != 1 or len(frames[0]) > DNetwork.MAX_MESSAGE_BYTES:
            raise TrackingError("invalid_response", DText.INVALID_RESPONSE)
        try:
            response = ZMQMsg.from_json(frames[0])
        except (ValueError, TypeError, UnicodeError) as error:
            raise TrackingError("invalid_response", DText.INVALID_RESPONSE) from error
        if response.sender != DTracking.SERVER or response.target != DTracking.CLIENT or response.method != method:
            raise TrackingError("invalid_response", DText.INVALID_RESPONSE)
        if response.payload.get("status") == "error":
            problem = response.payload.get("error")
            if not isinstance(problem, dict) or not isinstance(problem.get("code"), str):
                raise TrackingError("invalid_response", DText.INVALID_RESPONSE)
            try:
                key = DText(problem["message_key"])
            except (KeyError, ValueError, TypeError) as error:
                raise TrackingError("invalid_response", DText.INVALID_RESPONSE) from error
            raise TrackingError(problem["code"], key)
        if response.payload.get("status") != "ok" or not isinstance(response.payload.get("result"), dict):
            raise TrackingError("invalid_response", DText.INVALID_RESPONSE)
        return response.payload["result"]
