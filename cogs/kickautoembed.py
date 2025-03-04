from bot.classes import BaseAutoEmbed


class KickAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.kick, always_embed=True)
