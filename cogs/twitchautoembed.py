from interactions import Extension
from bot.tools import AutoEmbedder
import logging


class TwitchAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.twitch, logging.getLogger(__name__))
