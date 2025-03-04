from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(VimeoAutoEmbed(bot))


class VimeoAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.vimeo)
