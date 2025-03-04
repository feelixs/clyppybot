from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools.embedder import AutoEmbedder
from bot.env import EMBED_TXT_COMMAND
import logging


class YtAutoEmbed(Extension):
    def __init__(self, bot):
        self.platform = self.bot.yt
        self.embedder = AutoEmbedder(bot, self.platform, logging.getLogger(__name__))

    # don't auto embed yt links, should only work via /embed command
    @listen(MessageCreate)
    async def on_message_create(self, event):
        message_is_embed_command = (event.message.content.startswith(f"{EMBED_TXT_COMMAND} ")  # support text command (!embed url)
                                   and self.platform.is_clip_link(event.message.content.split(" ")[-1]))
        if self.platform.is_dl_server(event.message.guild) or message_is_embed_command:
            await self.embedder.on_message_create(event, is_embed_text_command=message_is_embed_command)
