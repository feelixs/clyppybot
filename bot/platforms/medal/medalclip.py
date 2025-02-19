from bot.classes import BaseClip, DownloadResponse


class MedalClip(BaseClip):
    def __init__(self, slug):
        self._service = "medal"
        self._url = f"https://medal.tv/clips/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        dl = await super().dl_check_size(filename, dlp_format, can_send_files)
        if dl is not None:
            return dl
        return await super().download(filename, dlp_format, can_send_files)
