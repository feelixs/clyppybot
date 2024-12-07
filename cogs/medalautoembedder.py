from bot.tools import AutoEmbedder
import logging


class MedalAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        super().__init__(bot, platform_tools=bot.medal, logger=logging.getLogger(__name__))
