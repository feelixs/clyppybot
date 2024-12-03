
class DriverDownloadFailed(Exception):
    pass


class ClipNotExists(Exception):
    pass


def is_twitch_clip_link(message: str):
    "https://clips.twitch.tv/BombasticSuccessfulMonitorSoonerLater-19gZfam5vc-A5CFh"
    return message.startswith("https://www.twitch.tv/") or message.startswith("https://www.m.twitch.tv/") \
        or message.startswith("https://twitch.tv/") or message.startswith("https://m.twitch.tv/") \
        or message.startswith("https://clips.twitch.tv/") or message.startswith("https://m.clips.twitch.tv/") \
        or message.startswith("https://www.clips.twitch.tv/") or message.startswith("https://www.m.clips.twitch.tv/")
