from bot.classes import BaseAutoEmbed


def setup(bot):
    # Create a BaseAutoEmbed instance with the Twitch platform
    return BaseAutoEmbed(bot, bot.twitch, always_embed=True)
