"""Send local release metadata without changing refs or task timers."""

from devlog.constants.DRelease import DRelease
from devlog.constants.DTracking import DTracking, Method


class ReleaseSync:
    def __init__(self, local, client):
        self.local, self.client = local, client

    def run(self, releases):
        inserted = 0
        for release in releases:
            result = self.client.call(Method.RELEASE, {
                DTracking.REPOSITORY: self.local.repository.identity, **release,
            })
            inserted += int(result[DRelease.INSERTED])
        return inserted
