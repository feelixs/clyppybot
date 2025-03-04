from bot.classes import BaseAutoEmbed


class YtAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.yt)
