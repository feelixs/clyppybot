from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(YoupoAutoEmbed(bot))


class YoupoAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.youp)
