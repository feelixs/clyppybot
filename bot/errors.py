import os


class UploadFailed(Exception):
    pass


class UnknownError(Exception):
    pass


class InvalidClipType(Exception):
    pass


class VideoTooLong(Exception):
    """Raised when a video is longer than max allowed length when not using VIP tokens"""
    def __init__(self, video_dur):
        self.video_dur = video_dur
        super().__init__(f"Video duration ({video_dur} seconds) exceeds maximum allowed length")


class VideoLongerThanMaxLength(Exception):
    """Raised when even using VIP tokens, a video is longer than the complete max length"""
    def __init__(self, video_dur):
        self.video_dur = video_dur
        super().__init__(f"Video duration ({video_dur} seconds) exceeds maximum allowed length")


class YtDlpForbiddenError(Exception):
    pass


class UrlUnparsable(Exception):
    pass


class UnsupportedError(Exception):
    pass


class RemoteTimeoutError(Exception):
    """The url couldn't be read, resulting in the remote or yt-dlp returning timeout"""
    pass


class NoPermsToView(Exception):
    pass


class VideoSaidUnavailable(Exception):
    """Video said unavailable (not certain that it's deleted/removed"""
    pass


class VideoUnavailable(Exception):
    """Video definitely unavailable"""
    pass


class NoDuration(Exception):
    """Raised when the url might not be a video, but we don't know for sure"""
    pass


class DefinitelyNoDuration(Exception):
    """Raised when we know for a fact that it's not a video - and won't download it to manually check"""
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
        raise DefinitelyNoDuration
    elif 'Incomplete YouTube ID' in err:
        raise VideoUnavailable
    elif 'This clip is no longer available' in err:
        raise VideoUnavailable
    elif 'HTTP Error 404: Not Found' in err:
        raise VideoSaidUnavailable
    elif 'Video unavailable' in err:
        raise VideoSaidUnavailable
    elif 'Your IP address is blocked from accessing this post' in err:
        raise IPBlockedError
    elif 'https://www.facebook.com/checkpoint' in err:
        raise IPBlockedError
    elif 'You don\'t have permission' in err or "unable to view this" in err:
        raise NoPermsToView
    elif 'ERROR: Unsupported URL' in err or 'is not a valid URL' in err:
        raise UnsupportedError
    elif 'Read timed out.' in err:
        raise RemoteTimeoutError
    elif 'HTTP Error 403: Forbidden' in err or 'Use --cookies,' in err:
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
