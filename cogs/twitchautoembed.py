from bot.tools import AutoEmbedder
import logging


class TwitchAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        super().__init__(bot, bot.twitch, logging.getLogger(__name__))
