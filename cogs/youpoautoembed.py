from bot.classes import BaseAutoEmbed


class YoupoAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.youp)
