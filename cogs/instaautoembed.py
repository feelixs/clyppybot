from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(InstaAutoEmbed(bot))


class InstaAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.insta)
