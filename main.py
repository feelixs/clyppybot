from interactions import AutoShardedClient, Intents
from bot.classes import BaseAutoEmbed
from bot.platforms.dailymotion import DailymotionMisc
from bot.platforms.drive import GoogleDriveMisc
from bot.platforms.insta import InstagramMisc
from bot.platforms.tiktok import TikTokMisc
from bot.platforms.twitch import TwitchMisc
from bot.platforms.reddit import RedditMisc
from bot.platforms.bsky import BlueSkyMisc
from bot.platforms.vimeo import VimeoMisc
from bot.platforms.medal import MedalMisc
from bot.platforms.youtube import YtMisc
from bot.platforms.bili import BiliMisc
from bot.platforms.kick import KickMisc
from bot.platforms.phub import PhubMisc
from bot.platforms.youp import YoupoMisc
from bot.platforms.xvid import XvidMisc
from bot.platforms.nuuls import NuulsMisc
from bot.platforms.discord_attach import DiscordMisc
from bot.platforms.x import Xmisc
from bot.tools.misc import Tools
from bot.io import get_aiohttp_session
from bot.db import GuildDatabase
from aiohttp import FormData
from bot.io.cdn import CdnSpacesClient
import logging
import asyncio
import os


class BaseAutoEmbedForConsistency(BaseAutoEmbed):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.platform = None
        super().__init__(self)


async def save_to_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with get_aiohttp_session() as session:
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
    async with get_aiohttp_session() as session:
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

cdn_client = CdnSpacesClient()
Bot.cdn_client = cdn_client
Bot.base = BaseAutoEmbedForConsistency(bot=Bot)

Bot.twitch = TwitchMisc(bot=Bot)
Bot.kick = KickMisc(bot=Bot)
Bot.insta = InstagramMisc(bot=Bot)
Bot.medal = MedalMisc(bot=Bot)
Bot.dailymotion = DailymotionMisc(bot=Bot)
Bot.reddit = RedditMisc(bot=Bot)
Bot.yt = YtMisc(bot=Bot)
Bot.youp = YoupoMisc(bot=Bot)
Bot.x = Xmisc(bot=Bot)
Bot.xvid = XvidMisc(bot=Bot)
Bot.bsky = BlueSkyMisc(bot=Bot)
Bot.bili = BiliMisc(bot=Bot)
Bot.phub = PhubMisc(bot=Bot)
Bot.tiktok = TikTokMisc(bot=Bot)
Bot.nuuls = NuulsMisc(bot=Bot)
Bot.vimeo = VimeoMisc(bot=Bot)
Bot.drive = GoogleDriveMisc(bot=Bot)
Bot.dsc = DiscordMisc(bot=Bot)

Bot.platform_list = [Bot.twitch, Bot.kick, Bot.insta, Bot.medal, Bot.reddit, Bot.yt, Bot.x, Bot.bsky, Bot.tiktok,
                     Bot.xvid, Bot.phub, Bot.youp, Bot.vimeo, Bot.bili, Bot.dailymotion, Bot.drive, Bot.nuuls, Bot.dsc]

Bot.tools = Tools()
Bot.guild_settings = GuildDatabase(on_load=load_from_server, on_save=save_to_server)

Bot.currently_embedding = []  # used in embedder.py (AutoEmbedder) -> for quickembeds (and i guess also triggers for command embeds)
Bot.currently_downloading = []  # used in command embeds across all platforms
Bot.currently_embedding_users = []  # used for command embeds


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
    Bot.load_extension('cogs.nuulsautoembed')
    Bot.load_extension('cogs.youpoautoembed')
    Bot.load_extension('cogs.xvidautoembed')
    Bot.load_extension('cogs.dailymotionautoembed')
    Bot.load_extension('cogs.driveautoembed')
    Bot.load_extension('cogs.discordattach_embed')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
