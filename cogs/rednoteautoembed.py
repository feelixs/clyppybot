from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools import AutoEmbedder
import logging


class RedNoteAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.rednote, logging.getLogger(__name__))

    @listen(MessageCreate)
    async def on_message_create(self, event):
        await self.embedder.on_message_create(event)
