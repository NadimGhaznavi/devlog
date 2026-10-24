from devlog.entity.TrackingError import TrackingError


class TrackingHandler:
    def __init__(self, tracking, localizer):
        self.tracking, self.localizer = tracking, localizer

    def __call__(self, request):
        try:
            return {"status": "ok", "result": self.tracking.execute(request.method, request.payload)}
        except TrackingError as error:
            return {"status": "error", "error": {
                "code": error.code, "message_key": str(error.key),
                "message": self.localizer.text(error.key),
            }}
