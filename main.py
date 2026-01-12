from interactions import AutoShardedClient, Intents
from interactions.api.gateway.gateway import GatewayClient, OPCODE, FastJson
from bot.setup import init_misc
from bot.io import get_aiohttp_session
from bot.db import GuildDatabase
from aiohttp import FormData
from bot.io.cdn import CdnSpacesClient
import aiohttp
import logging
import asyncio
import sys
import os


def format_count(count: int) -> str:
    """Format a number with K/M suffix (e.g., 1004690 -> '1.0M')"""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


async def fetch_embed_count(client=None) -> str:
    """Fetch embed count from API (or use cached value) and return formatted string"""
    # Use cached value if available on bot
    if client and hasattr(client, 'cached_embed_count'):
        return f"{format_count(client.cached_embed_count)} videos saved"
    # Otherwise fetch fresh
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://clyppy.io/api/stats/embeds-count/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    count = data.get("count", 0)
                    return f"{format_count(count)} videos saved"
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
            data = FormData()
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


async def main():
    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()
    await Bot.astart(token=os.getenv('CLYPP_TOKEN'))


asyncio.run(main())
