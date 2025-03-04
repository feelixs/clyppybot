from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(DailymotionAutoEmbed(bot))


class DailymotionAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.dailymotion)
