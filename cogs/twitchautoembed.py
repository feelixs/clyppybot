from bot.classes import BaseAutoEmbed


class TwitchAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.twitch, always_embed=True)
