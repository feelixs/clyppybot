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
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'X-API-Key': os.getenv('clyppy_post_key')}
            with open("guild_settings.db", "rb") as f:
                files = {'file': f}
                await session.post('https://felixcreations.com/api/products/clyppy/save_db/',
                                   files=files, headers=headers, data={'env': env})
            logger.info("Database saved to server")
        except Exception as e:
            logger.error(f"Failed to save database to server: {e}")


async def load_from_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'X-API-Key': 'your-secret-key'}
            params = {'env': env}
            async with session.get('https://felixcreations.com/api/products/clyppy/get_db/',
                                   headers=headers,
                                   params=params) as response:
                if response.status == 200:
                    content = await response.read()
                    with open('guild_settings.db', 'wb') as f:
                        f.write(content)
            logger.info("Database loaded from server")
        except Exception as e:
            logger.error(f"Failed to get database from server: {e}")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

Bot.twitch = TwitchMisc()
Bot.kick = KickMisc()
Bot.tools = Tools()
Bot.guild_settings = GuildDatabase(on_load=load_from_server, on_save=save_to_server)


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitchautoembed')
    Bot.load_extension('cogs.kickautoembed')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
