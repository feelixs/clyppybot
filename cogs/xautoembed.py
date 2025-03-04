from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(XAutoEmbed(bot))


class XAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.x)
