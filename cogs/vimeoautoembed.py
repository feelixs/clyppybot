from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(VimeoAutoEmbed(bot))


class VimeoAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.vimeo)
