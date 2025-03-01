from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools.embedder import AutoEmbedder
import logging


class BlueSkyAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.bsky, logging.getLogger(__name__))

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if self.bot.bsky.is_dl_server(event.message.guild):
            await self.embedder.on_message_create(event)
