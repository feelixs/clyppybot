from bot.classes import BaseAutoEmbed


class XAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.x)
