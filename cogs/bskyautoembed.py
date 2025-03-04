from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(BlueSkyAutoEmbed(bot))


class BlueSkyAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.bsky)
