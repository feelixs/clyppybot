from bot.classes import BaseAutoEmbed


class RedditAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.reddit)
