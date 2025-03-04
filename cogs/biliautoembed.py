from bot.classes import BaseAutoEmbed


class BilibiliAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.bili)
