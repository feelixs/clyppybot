from interactions import AutoShardedClient, Intents
from interactions.api.gateway.gateway import GatewayClient, OPCODE, FastJson
from bot.setup import init_misc
from bot.io import get_aiohttp_session
from bot.db import GuildDatabase
from bot.io.cdn import CdnSpacesClient
from cogs.base import format_count
import aiohttp
import signal
import logging
import asyncio
import sys
import os


async def fetch_embed_count(client=None) -> str:
    """Fetch embed count from API (or use cached value) and return formatted string"""
    # Use cached value if available on bot
    if client and hasattr(client, 'cached_embed_count'):
        return format_count(client.cached_embed_count)
    # Otherwise fetch fresh
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://clyppy.io/api/stats/embeds-count/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    count = data.get("count", 0)
                    return format_count(count)
    except Exception:
        pass
    return "/help"


# Monkey-patch to show mobile status indicator
async def _identify_mobile(self) -> None:
    """Send an identify payload to the gateway with mobile browser."""
    if self.ws is None:
        raise RuntimeError

    # Fetch embed count for status
    status_text = await fetch_embed_count(self.state.client)

    presence = {
        "status": "online",
        "since": None,
        "activities": [
            {
                "name": status_text,
                "type": 0,  # Playing
            }
        ],
        "afk": False,
    }

    payload = {
        "op": OPCODE.IDENTIFY,
        "d": {
            "token": self.state.client.http.token,
            "intents": self.state.intents,
            "shard": self.shard,
            "large_threshold": 250,
            "properties": {
                "os": sys.platform,
                "browser": "Discord Android",
                "device": "Discord Android",
            },
            "presence": presence,
        },
        "compress": True,
    }
    serialized = FastJson.dumps(payload)
    await self.ws.send_str(serialized)
    self.state.wrapped_logger(
        logging.DEBUG, f"Identification payload sent to gateway, requesting intents: {self.state.intents}"
    )


GatewayClient._identify = _identify_mobile


async def save_to_server():
    env = 'test' if os.getenv('TEST') is not None else 'prod'
    async with get_aiohttp_session() as session:
        try:
            headers = {'X-API-Key': os.getenv('clyppy_post_key')}
            data = aiohttp.FormData()
            data.add_field('env', env)
            with open("guild_settings.db", "rb") as f:
                data.add_field('file', f)
                async with session.post(
                        url='https://felixcreations.com/api/products/clyppy/save_db/',
                        data=data,
                        headers=headers
                ) as response:
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
            async with session.get(
                    url='https://felixcreations.com/api/products/clyppy/get_db/',
                    headers=headers,
                    params=params
            ) as response:
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
Bot = init_misc(Bot)

Bot.guild_settings = GuildDatabase(on_load=load_from_server, on_save=save_to_server)


async def on_shutdown(bot):
    """Called when the bot is shutting down."""
    # Save analytics state before shutdown
    logger.info("Waiting for tasks to complete...")

    timeout = 120
    while timeout > 0:
        await asyncio.sleep(1)
        if len(bot.currently_embedding) == 0 and len(bot.currently_downloading) == 0:
            break
        timeout -= 1

    logger.info("Tasks complete..." if timeout > 0 else "Timeout reached while waiting for tasks to complete...")
    logger.info("Bot shutdown complete")


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal from Docker by converting to KeyboardInterrupt."""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    raise KeyboardInterrupt()


async def main():
    signal.signal(signal.SIGTERM, handle_sigterm)
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
