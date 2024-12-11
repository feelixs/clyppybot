from interactions import Extension, listen
from interactions.api.events import MessageCreate
import logging


class Watch(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if "clyppy" in event.message.content or '1111723928604381314' in event.message.content:
            self.logger.info(f"{event.message.guild.name}: #{event.message.channel.name} "
                             f"@{event.message.author.username} - \"{event.message.content}\"")
        if '1111723928604381314' in event.message.content:
            await event.message.reply("shut up")
            