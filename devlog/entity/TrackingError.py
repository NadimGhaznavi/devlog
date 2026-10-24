from devlog.constants.DText import DText


class TrackingError(Exception):
    """An expected domain rejection, with a stable code and localized text key."""

    def __init__(self, code: str, key: DText):
        super().__init__(code)
        self.code = code
        self.key = key
