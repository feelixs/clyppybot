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


async def cleanup_old_videos():
    """Background task to periodically delete old video files."""
    cleanup_logger = logging.getLogger("video_cleanup")
    DEFAULT_EDIT_WAIT = 60 * 2  # 2 minutes
    MIN_FILE_AGE = 60 * 10  # 10 minutes

    while True:
        try:
            await asyncio.sleep(DEFAULT_EDIT_WAIT)
            this_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
            cleanup_logger.info(f"Checking {this_dir} for videos to delete")
            current_time = asyncio.get_event_loop().time()

            files = os.listdir(this_dir)
            for file in files:
                if file.endswith(".mp4") or file.endswith(".m3u8"):
                    file_path = os.path.join(this_dir, file)
                    file_age = current_time - os.path.getctime(file_path)

                    if file_age < MIN_FILE_AGE:
                        cleanup_logger.info(f"Skipping {file} - too new (age: {file_age / 60:.1f} minutes)")
                        continue

                    cleanup_logger.info(f"Deleting {file} (age: {file_age / 60:.1f} minutes)")
                    os.remove(file_path)
        except asyncio.CancelledError:
            cleanup_logger.info("Video cleanup task cancelled")
            break
        except Exception as e:
            cleanup_logger.error(f"Error during cleanup: {str(e)}")


async def on_shutdown(bot):
    """Called when the bot is shutting down."""
    logger.info("Initiating graceful shutdown...")

    # Step 1: Set shutdown flag (no new tasks will be accepted)
    bot.is_shutting_down = True
    logger.info("Shutdown flag set - new tasks will be queued")

    # Step 2: Wait for current tasks to complete (with reasonable timeout)
    logger.info("Waiting for active tasks to complete...")
    timeout = 60 * 3  # 3 minutes max
    start_time = asyncio.get_event_loop().time()

    while timeout > 0:
        embedding_count = len(bot.currently_embedding)
        downloading_count = len(bot.currently_downloading)

        if embedding_count == 0 and downloading_count == 0:
            logger.info("All active tasks completed")
            break

        if asyncio.get_event_loop().time() - start_time > 10:
            # Log status every 10 seconds
            logger.info(f"Still waiting: {embedding_count} embedding, {downloading_count} downloading")
            start_time = asyncio.get_event_loop().time()

        await asyncio.sleep(1)
        timeout -= 1

    if timeout <= 0:
        logger.warning(f"Timeout reached - forcing shutdown with {len(bot.currently_embedding)} "
                      f"embedding and {len(bot.currently_downloading)} downloading tasks remaining")

    # Step 3: Save task queue to disk
    logger.info("Saving task queue...")
    queue_count = bot.task_queue.get_task_count()
    logger.info(f"Task queue: {queue_count[0]} quickembeds, {queue_count[1]} slash commands")
    bot.task_queue.save()

    # Step 4: Save database
    try:
        logger.info("Saving database...")
        await bot.guild_settings.save()
        logger.info("Database saved successfully")
    except Exception as e:
        logger.error(f"Failed to save database: {e}")

    # Step 5: Stop the bot
    logger.info("Stopping bot...")
    try:
        await bot.stop()
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")

    logger.info("Shutdown complete")


async def main():
    # Set up shutdown event
    shutdown_event = asyncio.Event()

    def handle_shutdown_signal():
        """Signal handler that triggers graceful shutdown."""
        logger.info("Received shutdown signal (SIGTERM/SIGINT), initiating graceful shutdown...")
        shutdown_event.set()

    # Register signal handlers using asyncio's mechanism
    # Use get_running_loop() since we're inside an async function
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_shutdown_signal)

    Bot.load_extension('cogs.base')
    Bot.load_extension('cogs.watch')
    await Bot.guild_settings.setup_db()

    # Load and process queued tasks from previous shutdown
    logger.info("Loading task queue from previous session...")
    Bot.task_queue.load()

    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_old_videos())
    bot_task = asyncio.create_task(Bot.astart(token=os.getenv('CLYPP_TOKEN')))

    try:
        # Wait for either the bot to finish or shutdown signal
        done, pending = await asyncio.wait(
            [bot_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )

        # If shutdown was triggered, cancel tasks
        if shutdown_event.is_set():
            logger.info("Shutdown event triggered, stopping bot...")

            # Cancel cleanup task
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

            # Cancel bot task
            if not bot_task.done():
                bot_task.cancel()
                try:
                    await bot_task
                except asyncio.CancelledError:
                    pass
        else:
            # Bot task completed naturally (shouldn't happen normally)
            logger.info("Bot task completed")
            cleanup_task.cancel()

    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        # Always run shutdown procedure
        await on_shutdown(Bot)


# Manually create and manage event loop to have full control over signal handling
# (asyncio.run() installs its own signal handlers that interfere with ours)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(main())
finally:
    try:
        # Cancel all remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Wait for all tasks to finish cancelling
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        # Shutdown async generators
        loop.run_until_complete(loop.shutdown_asyncgens())
        # Shutdown default executor
        loop.run_until_complete(loop.shutdown_default_executor())
    finally:
        loop.close()
