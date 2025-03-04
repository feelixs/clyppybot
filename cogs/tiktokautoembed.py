from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(TikTokAutoEmbed(bot))


class TikTokAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.tiktok)
