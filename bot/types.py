from dataclasses import dataclass
from typing import Optional


# Default user-agent for yt-dlp
YT_DLP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"


COLOR_RED = 16711680
COLOR_GREEN = 65280


@dataclass
class GuildType:
    id: int
    name: str
    is_dm: bool


@dataclass
class DownloadResponse:
    remote_url: Optional[str]
    local_file_path: Optional[str]
    duration: float
    width: int
    height: int
    filesize: float
    video_name: Optional[str]
    can_be_discord_uploaded: Optional[bool]


@dataclass
class LocalFileInfo:
    local_file_path: Optional[str]
    duration: float
    width: int
    height: int
    filesize: float
    video_name: Optional[str]
    can_be_discord_uploaded: Optional[bool]
