"""Application-owned, request-scoped locale selection and text lookup."""

import json
from pathlib import Path
import re
from string import Formatter


BMFORGE_COMPONENT = {"id": "bmforge.localization", "spec_version": "0.1.0"}
_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def normalize(tag):
    """Return a comparable BCP-47-style tag, or None for invalid inputs."""
    if not isinstance(tag, str):
        return None
    value = tag.strip().replace("_", "-")
    return value.lower() if _TAG.fullmatch(value) else None


def fields(template):
    """Allow simple named placeholders, not attribute/index expressions."""
    names = set()
    for _, field, format_spec, conversion in Formatter().parse(template):
        if field is None:
            continue
        if not _FIELD.fullmatch(field) or format_spec or conversion:
            raise ValueError(f"Unsupported translation placeholder: {field}")
        names.add(field)
    return names


class Localizer:
    """Read UTF-8 JSON message catalogues; locale is chosen per request."""

    def __init__(self, directory, *, default_language="en"):
        self._catalogues = {}
        self._tags = {}
        for file in sorted(Path(directory).glob("*.json")):
            tag = normalize(file.stem)
            if tag is None or tag in self._catalogues:
                raise ValueError(f"Invalid or duplicate language catalogue: {file.name}")
            values = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(values, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
            ):
                raise ValueError(f"Message catalogue must contain string pairs: {file.name}")
            self._catalogues[tag] = values
            self._tags[tag] = file.stem
        default = normalize(default_language)
        if default not in self._catalogues:
            raise ValueError(f"Missing default language catalogue: {default_language}")
        self.default_language = self._tags[default]
        self._default = default
        base = self._catalogues[default]
        for language, values in self._catalogues.items():
            if language == default:
                continue
            unknown = set(values) - set(base)
            if unknown:
                raise ValueError(f"Unexpected translation keys in {self._tags[language]}: {sorted(unknown)}")
            for key, message in values.items():
                if fields(message) != fields(base[key]):
                    raise ValueError(f"Translation placeholders differ for {self._tags[language]}:{key}")
        for key, message in base.items():
            fields(message)

    @property
    def languages(self):
        return tuple(self._tags.values())

    def _match(self, requested):
        candidate = normalize(requested)
        while candidate:
            if candidate in self._catalogues:
                return candidate
            candidate = candidate.rpartition("-")[0]
        return None

    def select(self, *, explicit=None, accept_language=""):
        """Explicit language wins; else honour Accept-Language quality and order."""
        if explicit is not None:
            match = self._match(explicit)
            return self._tags[match or self._default]
        preferences = []
        for position, token in enumerate(accept_language.split(",")):
            parts = [p.strip() for p in token.split(";")]
            if not parts or parts[0] == "*":
                continue
            quality = 1.0
            if len(parts) > 1:
                if len(parts) != 2 or not parts[1].lower().startswith("q="):
                    continue
                try:
                    quality = float(parts[1][2:])
                except ValueError:
                    continue
            if not 0 < quality <= 1:
                continue
            preferences.append((-quality, position, parts[0]))
        for _, _, language in sorted(preferences):
            match = self._match(language)
            if match:
                return self._tags[match]
        return self.default_language

    def text(self, key, *, locale=None, **values):
        """Lookup by stable key (str or StrEnum); fall back per missing message."""
        key = key.value if hasattr(key, "value") else key
        fallback = self._catalogues[self._default][key]
        match = self._match(locale) if locale is not None else None
        message = self._catalogues[match].get(key, fallback) if match else fallback
        return message.format_map(values)
