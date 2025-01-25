from bot.classes import BaseClip


class MedalClip(BaseClip):
    def __init__(self, slug):
        self._service = "medal"
        self._url = f"https://medal.tv/clips/{slug}"
        self._title = None
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    @property
    def title(self) -> str:
        return self._title
