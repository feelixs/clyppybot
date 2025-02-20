from interactions import AutoShardedClient, Intents
from bot.platforms.twitch import TwitchMisc
from bot.platforms.medal import MedalMisc
from bot.platforms.kick import KickMisc
from bot.platforms.reddit import RedditMisc
from bot.platforms.insta import InstagramMisc
from bot.platforms.tiktok import TikTokMisc
from bot.platforms.youtube import YtMisc
from bot.platforms.x import Xmisc
from bot.platforms.bsky import BlueSkyMisc
from bot.platforms.bili import BiliMisc
from bot.platforms.vimeo import VimeoMisc
from bot.platforms.phub import PhubMisc
from bot.tools import Tools
from bot.db import GuildDatabase
from aiohttp import FormData, ClientSession
import logging
import asyncio
import os


async def save_to_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with ClientSession() as session:
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
    async with ClientSession() as session:
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
Bot.insta = InstagramMisc()
Bot.medal = MedalMisc()
Bot.reddit = RedditMisc()
Bot.yt = YtMisc()
Bot.x = Xmisc()
Bot.bsky = BlueSkyMisc()
Bot.bili = BiliMisc()
Bot.phub = PhubMisc()
Bot.tiktok = TikTokMisc()
Bot.vimeo = VimeoMisc()
Bot.platform_list = [Bot.twitch, Bot.kick, Bot.insta, Bot.medal, Bot.reddit, Bot.yt, Bot.x, Bot.bsky, Bot.tiktok,
                     Bot.phub, Bot.vimeo, Bot.bili]

Bot.tools = Tools()
Bot.guild_settings = GuildDatabase(on_load=load_from_server, on_save=save_to_server)


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitchautoembed')
    Bot.load_extension('cogs.kickautoembed')
    Bot.load_extension('cogs.vimeoautoembed')
    Bot.load_extension('cogs.tiktokautoembed')
    Bot.load_extension('cogs.medalautoembed')
    Bot.load_extension('cogs.phubautoembed')
    Bot.load_extension('cogs.instaautoembed')
    Bot.load_extension('cogs.redditautoembed')
    Bot.load_extension('cogs.ytautoembed')
    Bot.load_extension('cogs.xautoembed')
    Bot.load_extension('cogs.biliautoembed')
    Bot.load_extension('cogs.bskyautoembed')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
