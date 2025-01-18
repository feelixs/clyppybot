from bot.classes import BaseClip


class MedalClip(BaseClip):
    def __init__(self, slug):
        super().__init__(slug)
        self.service = "medal"
        self.url = f"https://medal.tv/clips/{slug}"
