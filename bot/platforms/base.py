from bot.env import EXTRA_YT_DLP_SUPPORTED_NSFW_DOMAINS, NSFW_DOMAIN_TRIGGERS
from bot.classes import BaseMisc, BaseClip
from bot.types import DownloadResponse
from bot.errors import VideoTooLong
from urllib.parse import urlparse


COOKIES_PLATFORMS = ['facebook']


class BASIC_MISC(BaseMisc):
    """Raw implementation for usage in BaseAutoEmbed (bot.base)"""
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "base"

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False):
        # enable cookies without needing to make a new file for a site
        cookies = any(domain in url for domain in COOKIES_PLATFORMS)
        valid, tokens_used, duration = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong(duration)
        self.logger.info(f"{url} is_shortform=True")
        return BASIC_CLIP(url, self.cdn_client, tokens_used, duration)

    def parse_clip_url(self, url: str, extended_url_formats=False):
        if 'http' not in url:
            return None

        parse = urlparse(url)
        netloc = parse.netloc.lower()

        # check if the netloc contains any nsfw trigger word
        self.is_nsfw = any(trigger in netloc for trigger in NSFW_DOMAIN_TRIGGERS)

        # if it doesn't, check if any of the known nsfw domains are in the netloc
        if not self.is_nsfw:
            self.is_nsfw = any(trigger in netloc for trigger in EXTRA_YT_DLP_SUPPORTED_NSFW_DOMAINS)

        return url


class BASIC_CLIP(BaseClip):
    def __init__(self, url: str, cdn_client, tokens_used: int, duration: int):
        self._service = 'base'
        self._url = url
        super().__init__(url, cdn_client, tokens_used, duration)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        cookies = any(domain in self.url for domain in COOKIES_PLATFORMS)
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
