from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools import AutoEmbedder
import logging


class XAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.x, logging.getLogger(__name__))

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if self.bot.x.is_dl_server(event.guild):
            await self.embedder.on_message_create(event)
