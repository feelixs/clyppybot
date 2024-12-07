from interactions import Extension
from bot.tools import AutoEmbedder
import logging


class MedalAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.medal, logging.getLogger(__name__))
