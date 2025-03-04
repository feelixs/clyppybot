from bot.classes import BaseClip
from bot.types import DownloadResponse


class MedalClip(BaseClip):
    def __init__(self, slug, cdn_client):
        self._service = "medal"
        self._url = f"https://medal.tv/clips/{slug}"
        super().__init__(slug, cdn_client)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
        if dl is not None:
            return dl
        return await super().download(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
