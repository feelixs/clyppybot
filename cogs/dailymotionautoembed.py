from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(DailymotionAutoEmbed(bot))


class DailymotionAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.dailymotion)
