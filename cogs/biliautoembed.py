from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(BilibiliAutoEmbed(bot))


class BilibiliAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.bili)
