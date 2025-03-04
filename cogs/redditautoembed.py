from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.load_extension(RedditAutoEmbed(bot))


class RedditAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.reddit)
