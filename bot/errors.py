import os


class UploadFailed(Exception):
    pass


class UnknownError(Exception):
    pass


class InvalidClipType(Exception):
    pass


class VideoTooLong(Exception):
    pass


class YtDlpForbiddenError(Exception):
    pass


class UrlUnparsable(Exception):
    pass


class UnsupportedError(Exception):
    pass


class NoPermsToView(Exception):
    pass


class VideoSaidUnavailable(Exception):
    pass


class NoDuration(Exception):
    # possibly no duration
    pass


class DefinitelyNoDuration(Exception):
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


class IPBlockedError(Exception):
    pass


class RateLimitExceededError(Exception):
    def __init__(self, resets_when, *args):
        super().__init__(*args)
        self.resets_when = resets_when


def handle_yt_dlp_err(err: str, file_path: str = None):
    if 'Duration: N/A, bitrate: N/A' in err:
        raise NoDuration
    elif 'No video could be found in this tweet' in err:
        return DefinitelyNoDuration
    elif 'HTTP Error 404: Not Found' in err:
        raise VideoSaidUnavailable
    elif 'Your IP address is blocked from accessing this post' in err:
        raise IPBlockedError
    elif 'You don\'t have permission' in err or "unable to view this" in err:
        raise NoPermsToView
    elif 'Video unavailable' in err:
        raise VideoSaidUnavailable
    elif 'ERROR: Unsupported URL' in err or 'is not a valid URL' in err:
        raise UnsupportedError
    elif 'Unable to download webpage: HTTP Error 403: Forbidden' in err:
        raise YtDlpForbiddenError
    elif 'Temporary failure in name resolution' in err or 'Name or service not known' in err:
        raise UrlUnparsable
    elif 'MoviePy error: failed to read the first frame of video file' in err:
        if file_path is not None:  # this can be raised after the file is partially downloaded
            try:
                os.remove(file_path)
            except:
                pass
        raise InvalidFileType
    elif 'label empty or too long' in err:
        raise UrlUnparsable
    elif 'Error passing `ffmpeg -i` command output:' in err or 'At least one output file must be specified' in err:
        raise InvalidFileType
    raise
