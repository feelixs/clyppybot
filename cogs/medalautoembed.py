from bot.classes import BaseAutoEmbed
from interactions import Extension, listen
from interactions.api.events import MessageCreate


class MedalAutoEmbed(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.auto_embed = BaseAutoEmbed(bot, bot.medal)
    
    @listen(MessageCreate)
    async def on_message_create(self, event):
        await self.auto_embed.handle_message(event)
