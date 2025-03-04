from bot.classes import BaseAutoEmbed


class BlueSkyAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.bsky)
