from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(InstaAutoEmbed(bot))


class InstaAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.insta)
