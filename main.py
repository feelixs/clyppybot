from interactions import AutoShardedClient, Intents
from bot.db import GuildDatabase
from bot.twitch import TwitchMisc
from bot.tools import Tools
from bot.kick import KickMisc
import logging
import asyncio
import os
import aiohttp


async def save_to_server():
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'X-API-Key': os.getenv('clyppy_post_key')}
            with open("guild_settings.db", "rb") as f:
                files = {'file': f}
                await session.post('https://felixcreations.com/api/products/clyppy/save_db/',
                                   data=files, headers=headers)

        except Exception as e:
            logger.error(f"Failed to save database to server: {e}")


async def load_from_server():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://example.com/directory/guild_settings.db') as response:
                if response.status == 200:
                    db_bytes = await response.read()
                    async with aiofiles.open("guild_settings.db", 'wb') as f:
                        await f.write(db_bytes)
        except Exception as e:
            logger.error(f"Failed to load database from server: {e}")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

Bot.twitch = TwitchMisc()
Bot.kick = KickMisc()
Bot.tools = Tools()
Bot.guild_settings = GuildDatabase(on_load=None, on_save=None)


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitchautoembed')
    Bot.load_extension('cogs.kickautoembed')
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
