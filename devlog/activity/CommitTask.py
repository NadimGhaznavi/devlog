"""Coordinate a local Git commit with service-owned task completion."""

from devlog.constants.DText import DText
from devlog.constants.DTracking import DTracking, Method, TaskStatus
from devlog.entity.TrackingError import TrackingError


class CommitTask:
    def __init__(self, local, client):
        self.local, self.client = local, client

    def run(self, message, *, record=None, completed=lambda result: None):
        repository = self.local.repository.identity
        sha, actual_message = self.local.commit_details(record) if record else (None, message)
        if not isinstance(actual_message, str) or not actual_message.strip() or len(actual_message.encode("utf-8")) > DTracking.MAX_COMMIT_MESSAGE:
            raise TrackingError("commit_message", DText.COMMIT_MESSAGE)
        prepare = {DTracking.REPOSITORY: repository, DTracking.PHASE: DTracking.PREPARE}
        if sha:
            prepare[DTracking.COMMIT_SHA] = sha
        task = self.client.call(Method.COMMIT, prepare)
        if task["status"] == TaskStatus.COMPLETED:
            completed({**task, DTracking.COMMIT_SHA: sha})
            return ()

        def finish(commit_sha):
            try:
                _, stored_message = self.local.commit_details(commit_sha)
                result = self.client.call(Method.COMMIT, {
                    DTracking.REPOSITORY: repository, DTracking.PHASE: DTracking.COMPLETE,
                    DTracking.TASK_ID: task["task_id"], DTracking.COMMIT_SHA: commit_sha,
                    DTracking.MESSAGE: stored_message,
                })
            except Exception as error:
                # Git has already committed; preserve and identify the exact recoverable result.
                raise CommitRecordingError(commit_sha) from error
            completed(result)

        if record:
            finish(sha)
            return ()
        return self.local.git.commit(message, on_committed=finish)


class CommitRecordingError(RuntimeError):
    def __init__(self, commit_sha):
        super().__init__(commit_sha)
        self.commit_sha = commit_sha
        self.key = DText.RECOVERY
