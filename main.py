from interactions import AutoShardedClient, Intents
from bot.db import GuildDatabase
from bot.twitch import TwitchMisc
from bot.medal import MedalMisc
from bot.tools import Tools
from bot.kick import KickMisc
from bot.reddit import RedditMisc
from bot.youtube import YtMisc
import logging
import asyncio
import os
import aiohttp
from aiohttp import FormData


async def save_to_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'X-API-Key': os.getenv('clyppy_post_key')}
            data = FormData()
            data.add_field('env', env)
            with open("guild_settings.db", "rb") as f:
                data.add_field('file', f)
                async with session.post('https://felixcreations.com/api/products/clyppy/save_db/',
                                        data=data, headers=headers) as response:
                    if response.status == 200:
                        logger.info("Database saved to server")
                    else:
                        logger.error(f"Failed with status {response.status}")
        except Exception as e:
            logger.error(f"Failed to save database to server: {e}")


async def load_from_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'X-API-Key': os.getenv('clyppy_post_key')}
            params = {'env': env}
            async with session.get('https://felixcreations.com/api/products/clyppy/get_db/',
                                   headers=headers,
                                   params=params) as response:
                if response.status == 200:
                    content = await response.read()
                    with open('guild_settings.db', 'wb') as f:
                        f.write(content)
                    logger.info("Database loaded from server")
                else:
                    logger.error(f"Failed to get database from server: {response.status}")
        except Exception as e:
            logger.error(f"Failed to get database from server: {e}")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

Bot.twitch = TwitchMisc()
Bot.kick = KickMisc()
Bot.medal = MedalMisc()
Bot.medal = RedditMisc()
Bot.yt = YtMisc()
Bot.tools = Tools()
Bot.guild_settings = GuildDatabase(on_load=load_from_server, on_save=save_to_server)


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitchautoembed')
    Bot.load_extension('cogs.kickautoembed')
    Bot.load_extension('cogs.medalautoembed')
    Bot.load_extension('cogs.redditautoembed')
    Bot.load_extension('cogs.ytautoembed')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
