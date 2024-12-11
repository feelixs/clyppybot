from interactions import Extension, listen
from interactions.api.events import MessageCreate
import logging


class Watch(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if "clyppy" in event.message.content:
            self.logger.info(f"{event.guild.name}: #{event.channel.name} @{event.author.username} - \"{event.message.content}\"")
