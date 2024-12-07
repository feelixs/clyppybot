from interactions import Extension
from bot.tools import AutoEmbedder
import logging


class KickAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.kick, logging.getLogger(__name__))
