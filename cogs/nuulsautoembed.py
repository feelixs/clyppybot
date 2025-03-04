from bot.classes import BaseAutoEmbed
from interactions import Extension, listen
from interactions.api.events import MessageCreate


class NuulsAutoEmbed(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.platform = bot.nuuls
        self.auto_embed = BaseAutoEmbed(self)
    
    @listen(MessageCreate)
    async def on_message_create(self, event):
        await self.auto_embed.handle_message(event)
