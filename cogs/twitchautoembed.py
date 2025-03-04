from bot.classes import BaseAutoEmbed

# We'll directly use the BaseAutoEmbed class since it already has all the functionality
# we need, and just needs to be initialized with the right platform and always_embed flag

def setup(bot):
    # Create a BaseAutoEmbed instance with the Twitch platform
    return BaseAutoEmbed(bot, bot.twitch, always_embed=True)
