from interactions import AutoShardedClient, Intents
from bot.twitch import TwitchMisc
import logging
import asyncio
import os


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")
Bot = AutoShardedClient(intents=Intents.DEFAULT | Intents.MESSAGE_CONTENT)

t = TwitchMisc(logger)
Bot.twitch = t



