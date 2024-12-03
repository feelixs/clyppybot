from interactions import Extension, Embed, slash_command, SlashContext, listen
from interactions.api.events.discord import GuildJoin, GuildLeft
from bot.tools import create_nexus_str
import logging
import aiohttp
import os


VERSION = "1.0b"


class Base(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.logger = logging.getLogger(__name__)

    @slash_command(name="help", description="Get help using CLYPPY")
    async def help(self, ctx: SlashContext):
        about = (
            "CLYPPY supports uploading Twitch clips in Full HD to your Discord channels! Send a valid Twitch Clip link to get started.\n\n"
            "**TROUBLESHOOTING**\nIf CLYPPY isn't responding to your Twitch Clip links, it could be because it has incorrect permissions for your Discord channel."
            " Required permissions are: `Attach Files`, `Send Messages`\n\n"
            "**UPDATE Dec 3rd 2024** CLYPPY is back online after a break. Currently, auto-compression has been disabled, so only smaller clips can be processed. We are working on improving the service and adding new features. Stay tuned!")
        help_embed = Embed(title="About CLYPPY", description=about)
        help_embed.description += create_nexus_str()
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(embed=help_embed)

    @listen()
    async def on_guild_join(self, event: GuildJoin):
        if self.ready:
            if os.getenv("TEST") is not None:
                await self.post_servers(len(self.bot.guilds))
            self.logger.info(f'Joined new guild: {event.guild.name}')

    @listen()
    async def on_guild_left(self, event: GuildLeft):
        if self.ready:
            self.logger.info(f'Left guild: {event.guild.name}')
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_ready(self):
        if not self.ready:
            self.ready = True
            self.logger.info(f"bot logged in as {self.bot.user.username}")
            self.logger.info(f"total shards: {len(self.bot.shards)}")
            self.logger.info(f"my guilds: {len(self.bot.guilds)}")
            self.logger.info("--------------")

    @staticmethod
    async def post_servers(num: int):
        async with aiohttp.ClientSession() as session:
            async with session.post("https://top.gg/api/bots/1111723928604381314/stats", json={'server_count': num},
                                    headers={'Authorization': os.getenv('GG_TOKEN')}) as resp:
                await resp.json()
