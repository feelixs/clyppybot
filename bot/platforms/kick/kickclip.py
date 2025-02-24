from bot.classes import BaseClip, DownloadResponse


class KickClip(BaseClip):
    def __init__(self, slug, user):
        self._service = "kick"
        self._url = f"https://kick.com/{user}/clips/clip_{slug}"
        self.user = user
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename: str = None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True, useragent=None) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        useragent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0'
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            useragent=useragent,
            upload_if_large=True
        )
