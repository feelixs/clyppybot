from bot.tools import AutoEmbedder
import logging


class KickAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        super().__init__(bot, bot.kick, self.logger)
