from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(YtAutoEmbed(bot))


class YtAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.yt)
