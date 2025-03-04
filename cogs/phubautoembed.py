from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(PhubAutoEmbed(bot))


class PhubAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.phub)
