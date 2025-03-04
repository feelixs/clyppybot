from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(KickAutoEmbed(bot))


class KickAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.kick, always_embed=True)
