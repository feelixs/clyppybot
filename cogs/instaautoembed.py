from bot.classes import BaseAutoEmbed


class InstaAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.insta)
