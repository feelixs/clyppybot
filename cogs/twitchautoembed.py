from bot.tools import AutoEmbedder
import logging


class TwitchAutoEmbed(AutoEmbedder):
    def __init__(self, bot):
        if not hasattr(bot, 'twitch') or bot.twitch is None:
            raise AttributeError("Bot instance does not have 'twitch' set. Cannot initialize TwitchAutoEmbed.")

        super().__init__(bot, bot.twitch, logging.getLogger(__name__))
