from bot.classes import BaseAutoEmbed


class DailymotionAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.dailymotion)
