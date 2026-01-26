import asyncio
import signal
from interactions import AutoShardedClient, Intents, listen, Activity, ActivityType

from .config import config
from .logging_config import setup_logging, get_logger
from .api_client import close_api_client, get_api_client
from .services.session_reconciler import SessionReconciler
from .services.task_manager import TaskManager
from .services.event_queue import close_event_queue, get_event_queue
from . import intent_flags

# Configure logging
setup_logging()
logger = get_logger("insightbot")


class InsightBot(AutoShardedClient):
    """Main bot client with lifecycle hooks."""

    async def on_startup(self) -> None:
        """Called when the bot is starting up."""
        logger.info("Bot startup complete")

    async def on_shutdown(self) -> None:
        """Called when the bot is shutting down."""
        # Flush event queue before shutdown
        logger.info("Flushing event queue...")
        try:
            from .tasks.event_queue_processor import EventQueueProcessor
            queue = get_event_queue()

            # Trigger final queue processing
            for ext in self.ext.values():
                if isinstance(ext, EventQueueProcessor):
                    await ext.process_queue()
                    break

            # Check remaining queue depth
            depths = await queue.get_queue_depth()
            if depths:
                logger.warning(f"Queue not empty at shutdown: {depths}")
            else:
                logger.info("Event queue fully drained")
        except Exception as e:
            logger.error(f"Failed to flush event queue: {e}")

        # Save analytics state before shutdown
        logger.info("Saving analytics state...")
        try:
            from .events.analytics_collector import AnalyticsCollector
            for ext in self.ext.values():
                if isinstance(ext, AnalyticsCollector):
                    ext.save_state()
                    break
        except Exception as e:
            logger.error(f"Failed to save analytics state: {e}")

        logger.info("Shutting down TaskManager...")
        task_manager = TaskManager.get()
        await task_manager.shutdown(timeout=30.0)
        logger.info("Closing event queue...")
        await close_event_queue()
        logger.info("Closing API client...")
        await close_api_client()
        logger.info("Bot shutdown complete")


def create_bot() -> InsightBot:
    """Create and configure the bot instance."""
    intents = (
        Intents.GUILDS
        | Intents.GUILD_MEMBERS
        | Intents.GUILD_MESSAGES
        | Intents.GUILD_VOICE_STATES
        | Intents.MESSAGE_CONTENT
        | Intents.GUILD_PRESENCES
    )

    bot = InsightBot(
        token=config.discord_token,
        intents=intents,
        activity=Activity(name="server stats", type=ActivityType.WATCHING),
    )

    return bot


bot = create_bot()


@listen()
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")

    # Check if privileged intents are actually granted and set global flags
    intent_flags.HAS_GUILD_PRESENCES = bool(bot.intents & Intents.GUILD_PRESENCES)
    intent_flags.HAS_GUILD_MEMBERS = bool(bot.intents & Intents.GUILD_MEMBERS)
    intent_flags.HAS_MESSAGE_CONTENT = bool(bot.intents & Intents.MESSAGE_CONTENT)

    if not intent_flags.HAS_GUILD_PRESENCES:
        logger.warning(
            "GUILD_PRESENCES intent is not enabled - online status tracking and game activity disabled. "
            "Enable it in the Discord Developer Portal."
        )
    if not intent_flags.HAS_GUILD_MEMBERS:
        logger.warning(
            "GUILD_MEMBERS intent is not enabled - member tracking may be incomplete. "
            "Enable it in the Discord Developer Portal."
        )
    if not intent_flags.HAS_MESSAGE_CONTENT:
        logger.warning(
            "MESSAGE_CONTENT intent is not enabled - message content will not be available. "
            "Enable it in the Discord Developer Portal."
        )

    # Initialize TaskManager and register task functions
    task_manager = TaskManager.get()
    api = get_api_client()
    task_manager.register("bulk_upsert_members", api.bulk_upsert_members)
    task_manager.register("bulk_upsert_roles", api.bulk_upsert_roles)
    task_manager.register("bulk_sync_member_roles", api.bulk_sync_member_roles)

    # Load and run any pending tasks from previous shutdown
    await task_manager.load_and_run_pending()

    # Reconcile sessions with Discord's current state
    try:
        result = await SessionReconciler.reconcile_all(bot)
        logger.info(
            f"Session reconciliation complete: "
            f"{result['voice_closed']} voice, {result['game_closed']} game sessions closed"
        )
    except Exception as e:
        logger.error(f"Session reconciliation failed: {e}")


@listen()
async def on_startup():
    """Called during bot startup."""
    await bot.on_startup()


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal from Docker by converting to KeyboardInterrupt."""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    raise KeyboardInterrupt()


def main():
    """Main entry point for the bot."""
    # Register SIGTERM handler for Docker graceful shutdown
    signal.signal(signal.SIGTERM, handle_sigterm)

    logger.info("Starting InsightBot...")

    # Load extensions
    bot.load_extension("bot.extensions.stats")
    bot.load_extension("bot.extensions.top")
    bot.load_extension("bot.extensions.counters")
    bot.load_extension("bot.extensions.admin")
    bot.load_extension("bot.extensions.games")
    bot.load_extension("bot.extensions.topics")

    # Load event handlers
    bot.load_extension("bot.events.messages")
    bot.load_extension("bot.events.voice")
    bot.load_extension("bot.events.presence")
    bot.load_extension("bot.events.members")

    # Load background tasks
    bot.load_extension("bot.tasks.counter_updater")
    bot.load_extension("bot.tasks.digest_scheduler")
    bot.load_extension("bot.tasks.event_queue_processor")

    # Load analytics collector
    bot.load_extension("bot.events.analytics_collector")

    # Load invite tracker
    bot.load_extension("bot.events.invite_tracker")

    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        asyncio.run(bot.on_shutdown())


if __name__ == "__main__":
    main()
