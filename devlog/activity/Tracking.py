"""Validate command payloads and invoke domain database operations."""

from datetime import datetime, timezone
import re

from devlog.constants.DText import DText
from devlog.constants.DRelease import DRelease
from devlog.constants.DTracking import DTracking, Method
from devlog.entity.TrackingError import TrackingError


class Tracking:
    def __init__(self, tasks):
        self.tasks = tasks

    def execute(self, method, payload):
        if method == Method.STATUS:
            if payload:
                raise TrackingError("invalid_request", DText.INVALID_REQUEST)
            return self.tasks.status()
        if method == Method.HEALTH:
            if payload:
                raise TrackingError("invalid_request", DText.INVALID_REQUEST)
            self.tasks.health()
            return {}
        repository = payload.get(DTracking.REPOSITORY)
        if not isinstance(repository, str) or not repository.strip() or len(repository) > DTracking.MAX_REPOSITORY:
            raise TrackingError("invalid_request", DText.INVALID_REQUEST)
        if any(ord(c) < 32 for c in repository):
            raise TrackingError("invalid_request", DText.INVALID_REQUEST)
        if method == Method.RELEASE:
            return self._record_release(repository, payload)
        if method == Method.START and set(payload) == {DTracking.REPOSITORY}:
            return self.tasks.start(repository)
        if method == Method.PAUSE and set(payload) == {DTracking.REPOSITORY}:
            return self.tasks.pause(repository)
        if method != Method.COMMIT:
            raise TrackingError("unknown_method", DText.INVALID_REQUEST)
        phase = payload.get(DTracking.PHASE)
        sha = payload.get(DTracking.COMMIT_SHA)
        if sha is not None and (not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None):
            raise TrackingError("invalid_request", DText.INVALID_REQUEST)
        if phase == DTracking.PREPARE and set(payload) <= {DTracking.REPOSITORY, DTracking.PHASE, DTracking.COMMIT_SHA}:
            return self.tasks.prepare_commit(repository, commit_sha=sha)
        if phase == DTracking.COMPLETE and set(payload) == {
            DTracking.REPOSITORY, DTracking.PHASE, DTracking.TASK_ID, DTracking.COMMIT_SHA, DTracking.MESSAGE,
        }:
            task_id, message = payload[DTracking.TASK_ID], payload[DTracking.MESSAGE]
            if type(task_id) is not int or task_id <= 0 or not sha or not isinstance(message, str) or not message.strip() or len(message.encode("utf-8")) > DTracking.MAX_COMMIT_MESSAGE:
                raise TrackingError("invalid_request", DText.INVALID_REQUEST)
            return self.tasks.complete(repository, task_id, sha, message)
        raise TrackingError("invalid_request", DText.INVALID_REQUEST)

    def _record_release(self, repository, payload):
        if set(payload) != {DTracking.REPOSITORY, DRelease.TAG_NAME, DRelease.CODENAME,
                            DTracking.COMMIT_SHA, DRelease.RELEASED_AT}:
            raise TrackingError("invalid_request", DText.INVALID_REQUEST)
        tag, codename, sha, timestamp = (payload[key] for key in (
            DRelease.TAG_NAME, DRelease.CODENAME, DTracking.COMMIT_SHA, DRelease.RELEASED_AT))
        if (not isinstance(tag, str) or len(tag.encode("utf-8")) > DRelease.MAX_TAG_BYTES
                or re.fullmatch(DRelease.TAG_PATTERN, tag) is None
                or (codename is not None and (not isinstance(codename, str) or not codename.strip()
                    or len(codename.encode("utf-8")) > DRelease.MAX_CODENAME_BYTES
                    or any(ord(c) < 32 or ord(c) == 127 for c in codename)))
                or not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None
                or not isinstance(timestamp, str) or len(timestamp) > 40):
            raise TrackingError("invalid_request", DText.INVALID_REQUEST)
        try:
            released_at = datetime.fromisoformat(timestamp)
            if released_at.tzinfo is None:
                raise ValueError("Release time requires an explicit UTC offset")
            released_at = released_at.astimezone(timezone.utc).replace(tzinfo=None)
            if released_at.year < DTracking.MIN_TIMING_YEAR:
                raise ValueError("Release time is outside the database range")
        except (ValueError, OverflowError) as error:
            raise TrackingError("invalid_request", DText.INVALID_REQUEST) from error
        return self.tasks.record_release(repository, tag, codename, sha, released_at)
