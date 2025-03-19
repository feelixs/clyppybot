from bot.env import EXTRA_YT_DLP_SUPPORTED_NSFW_DOMAINS, NSFW_DOMAIN_TRIGGERS
from bot.classes import BaseMisc, BaseClip
from bot.types import DownloadResponse
from bot.errors import VideoTooLong
from urllib.parse import urlparse


class BASIC_MISC(BaseMisc):
    """Raw implementation for usage in BaseAutoEmbed (bot.base)"""
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "base"

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False):
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")
        return BASIC_CLIP(url, self.cdn_client)

    def parse_clip_url(self, url: str, extended_url_formats=False):
        return url

    def is_nsfw(self, url: str = None):
        if url is None:
            raise Exception("BASIC_MISC.is_nsfw must include an url param")

        parse = urlparse(url)
        netloc = parse.netloc.lower()

        # check if the netloc contains any nsfw trigger word
        is_nsfw = any(trigger in netloc for trigger in NSFW_DOMAIN_TRIGGERS)
        if is_nsfw:
            return True

        # if it doesn't, check if any of the known nsfw domains are in the netloc
        return any(trigger in netloc for trigger in EXTRA_YT_DLP_SUPPORTED_NSFW_DOMAINS)


class BASIC_CLIP(BaseClip):
    def __init__(self, url: str, cdn_client):
        self._service = 'base'
        self._url = url
        super().__init__(url, cdn_client)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
