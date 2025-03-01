from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools.embedder import AutoEmbedder
import logging


class TwitchAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.twitch, logging.getLogger(__name__))

    @listen(MessageCreate)
    async def on_message_create(self, event):
        await self.embedder.on_message_create(event)
