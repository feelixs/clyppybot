from bot.classes import BaseAutoEmbed


class TikTokAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.tiktok)
