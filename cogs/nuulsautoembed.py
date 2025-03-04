from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(NuulsAutoEmbed(bot))


class NuulsAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.nuuls)
