from dataclasses import dataclass, field
import json
from typing import Any

from devlog.constants.DTracking import DTracking


@dataclass
class ZMQMsg:
    sender: str
    method: str
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for value in (self.sender, self.method):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("sender and method must be nonempty strings")
        if self.target is not None and not isinstance(self.target, str):
            raise ValueError("target must be a string or null")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be an object")

    def to_json(self):
        return json.dumps(dict(protocol_version=DTracking.PROTOCOL_VERSION, sender=self.sender,
                               target=self.target, method=self.method, payload=self.payload),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    @classmethod
    def from_json(cls, raw):
        values = json.loads(raw.decode("utf-8"), parse_constant=lambda value: cls._invalid_number(value))
        # Escaped lone surrogates survive JSON decoding but cannot be encoded
        # as UTF-8 in outgoing messages or persistence. Reject at the boundary,
        # including nested values and object keys, before activity dispatch.
        try:
            json.dumps(values, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (UnicodeError, ValueError) as error:
            raise ValueError("Invalid Unicode in message envelope") from error
        if not isinstance(values, dict) or set(values) != {"protocol_version", "sender", "target", "method", "payload"}:
            raise ValueError("Invalid message envelope")
        version = values.pop("protocol_version")
        if type(version) is not int or version != DTracking.PROTOCOL_VERSION:
            raise ValueError("Unsupported protocol version")
        return cls(**values)

    @staticmethod
    def _invalid_number(value):
        raise ValueError("Non-finite JSON numbers are not supported")
