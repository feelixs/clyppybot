from bot.classes import BaseAutoEmbed


class VimeoAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.vimeo)
