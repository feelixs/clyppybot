class UploadFailed(Exception):
    pass


class UnknownError(Exception):
    pass


class InvalidClipType(Exception):
    pass


class VideoTooLong(Exception):
    pass


class NoPermsToView(Exception):
    pass


class NoDuration(Exception):
    pass


class InvalidFileType(Exception):
    pass


class ClipFailure(Exception):
    pass


class DriverDownloadFailed(Exception):
    pass


class FailedTrim(Exception):
    pass


class FailureHandled(Exception):
    pass


class ClipNotExists(Exception):
    pass


class TooManyTriesError(Exception):
    """Exception raised when the maximum number of retries is exceeded."""
    pass


class RateLimitExceededError(Exception):
    def __init__(self, resets_when, *args):
        super().__init__(*args)
        self.resets_when = resets_when
