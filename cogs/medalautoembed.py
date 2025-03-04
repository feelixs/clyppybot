from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(MedalAutoEmbed(bot))


class MedalAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.medal)
