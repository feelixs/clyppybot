from bot.tools import AutoEmbedder
import logging


class TwitchAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        super().__init__(bot, bot.twitch, self.logger)
