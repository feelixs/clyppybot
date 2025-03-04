from bot.classes import BaseAutoEmbed


class TwitchAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, self.bot.twitch, always_embed=True)
