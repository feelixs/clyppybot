"""Channel event handlers."""

from interactions import Extension, listen, PermissionOverwrite
from interactions.api.events import ChannelCreate, ChannelUpdate, ChannelDelete

from ..logging_config import get_logger
from ..services.event_queue import get_event_queue, EVENT_CHANNEL_UPSERT, EVENT_CHANNEL_DELETE

logger = get_logger("insightbot.events.channels")


class ChannelEvents(Extension):
    """Handle channel-related events."""

    def _serialize_permission_overwrites(self, overwrites: list[PermissionOverwrite]) -> list[dict]:
        """Convert Discord permission overwrites to API format."""
        result = []
        for ow in overwrites:
            result.append({
                "target_type": "role" if ow.type == 0 else "member",
                "target_id": int(ow.id),
                "allow_bits": int(ow.allow),
                "deny_bits": int(ow.deny),
            })
        return result

    async def _sync_channel(self, channel):
        """Enqueue a channel upsert event."""
        if not channel.guild:
            return  # Skip DM channels

        try:
            guild_id = int(channel.guild.id)
            channel_id = int(channel.id)
            queue = get_event_queue()

            # Get permission overwrites
            permission_overwrites = []
            if hasattr(channel, 'permission_overwrites') and channel.permission_overwrites:
                permission_overwrites = self._serialize_permission_overwrites(channel.permission_overwrites)

            # Get parent_id (for channels in categories)
            parent_id = None
            if hasattr(channel, 'parent_id') and channel.parent_id:
                parent_id = int(channel.parent_id)

            # Get topic (for text channels)
            topic = None
            if hasattr(channel, 'topic'):
                topic = channel.topic

            # Get NSFW flag
            is_nsfw = False
            if hasattr(channel, 'nsfw'):
                is_nsfw = channel.nsfw

            # Enqueue channel upsert event
            await queue.enqueue(EVENT_CHANNEL_UPSERT, {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "name": channel.name,
                "channel_type": int(channel.type),
                "topic": topic,
                "position": channel.position if hasattr(channel, 'position') else None,
                "parent_id": parent_id,
                "is_nsfw": is_nsfw,
                "permission_overwrites": permission_overwrites,
            })

            logger.debug(f"Enqueued channel upsert for {channel.name} ({channel_id}) in guild {guild_id}")

        except Exception as e:
            logger.error(f"Failed to enqueue channel upsert for {channel.id}: {e}")

    @listen(ChannelCreate)
    async def on_channel_create(self, event: ChannelCreate):
        """Track when a channel is created."""
        await self._sync_channel(event.channel)

    @listen(ChannelUpdate)
    async def on_channel_update(self, event: ChannelUpdate):
        """Track when a channel is updated."""
        await self._sync_channel(event.after)

    @listen(ChannelDelete)
    async def on_channel_delete(self, event: ChannelDelete):
        """Track when a channel is deleted."""
        if not event.channel.guild:
            return  # Skip DM channels

        try:
            channel_id = int(event.channel.id)
            queue = get_event_queue()

            # Enqueue channel delete event
            await queue.enqueue(EVENT_CHANNEL_DELETE, {
                "channel_id": channel_id,
            })

            logger.debug(f"Enqueued channel delete for {event.channel.name} ({channel_id})")

        except Exception as e:
            logger.error(f"Failed to enqueue channel delete for {event.channel.id}: {e}")
