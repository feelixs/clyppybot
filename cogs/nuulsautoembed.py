from bot.classes import BaseAutoEmbed


class NuulsAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.nuuls)
