from bot.classes import BaseAutoEmbed


class PhubAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.phub)
