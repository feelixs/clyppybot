from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools import AutoEmbedder
import logging


class YtAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.yt, logging.getLogger(__name__))

    # don't auto embed yt links, should only work via /embed command
    @listen(MessageCreate)
    async def on_message_create(self, event):
        if self.bot.yt.is_dl_server(event.message.guild):
            await self.embedder.on_message_create(event)

    @listen()
    async def on_raw_gateway_event(event):
        if event.name == "INVITE_CREATE":
            print(f"Raw invite data received: {event.data}")
