from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(XvidAutoEmbed(bot))


class XvidAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.xvid)
