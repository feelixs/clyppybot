from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(TwitchAutoEmbed(bot))


class TwitchAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.twitch, always_embed=True)
