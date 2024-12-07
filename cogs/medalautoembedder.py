from bot.tools import AutoEmbedder
import logging


class MedalAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        super().__init__(bot, bot.medal, logging.getLogger(__name__))
