from bot.classes import BaseAutoEmbed


def setup(bot):
    # Create a BaseAutoEmbed instance with the Kick platform
    return BaseAutoEmbed(bot, bot.kick, always_embed=True)
