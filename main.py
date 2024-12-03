from interactions import AutoShardedClient, Intents
from bot.twitch import TwitchMisc
import logging
import asyncio
import os


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

t = TwitchMisc()
Bot.twitch = t


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.twitch_autoembed')
    Bot.load_extension('cogs.kick_autoembed')
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
