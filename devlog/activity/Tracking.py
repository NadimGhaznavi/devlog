"""Validate command payloads and invoke domain database operations."""

import re

from devlog.constants.DText import DText
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
