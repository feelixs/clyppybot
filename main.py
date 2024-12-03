from interactions import AutoShardedClient, Intents
from bot.twitch import TwitchMisc
from bot.kick import KickMisc
import logging
import asyncio
import os


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

t = TwitchMisc()
k = KickMisc()
Bot.twitch = t
Bot.kick = k


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitchautoembed')
    Bot.load_extension('cogs.kickautoembed')
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
