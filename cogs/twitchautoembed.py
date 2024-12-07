from bot.tools import AutoEmbedder
import logging


class TwitchAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        super().__init__(bot, platform_tools=bot.twitch, logger=logging.getLogger(__name__))
