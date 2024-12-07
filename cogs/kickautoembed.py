from bot.tools import AutoEmbedder
import logging


class KickAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        super().__init__(bot, platform_tools=bot.kick, logger=logging.getLogger(__name__))
