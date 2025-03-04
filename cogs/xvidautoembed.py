from bot.classes import BaseAutoEmbed


class XvidAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.xvid)
