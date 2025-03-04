from bot.classes import BaseAutoEmbed


class MedalAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.medal)
