import re
from typing import Optional, List
from dataclasses import dataclass
from interactions import Guild, GuildVoice
from interactions.client.errors import Forbidden, NotFound

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.services.counter")


@dataclass
class CounterInfo:
    """Counter channel information."""

    id: int
    guild_id: int
    channel_id: int
    counter_type: str
    template: str
    role_id: Optional[int]
    goal_target: Optional[int]
    last_value: Optional[int]


class CounterService:
    """Service for managing counter channels."""

    COUNTER_TYPES = ["members", "online", "boosts", "role", "voice", "goal"]

    @staticmethod
    async def get_all_values(
        guild: Guild,
        role_id: Optional[int] = None,
        goal_target: Optional[int] = None,
    ) -> dict[str, int]:
        """Get all keyword values for a guild."""
        api = get_api_client()

        values = {
            "members": guild.member_count or 0,
            "online": sum(1 for p in guild.presences if p.get('status') in ['online', 'idle', 'dnd']),
            "boosts": guild.premium_subscription_count or 0,
            "voice": await api.get_active_voice_count(int(guild.id)),
        }

        if role_id and guild.members:
            values["role"] = sum(1 for m in guild.members if any(r.id == role_id for r in m.roles))
        else:
            values["role"] = 0

        if goal_target:
            values["goal"] = goal_target
        else:
            values["goal"] = 0

        return values

    @staticmethod
    def _extract_keywords(template: str) -> set[str]:
        """Extract keyword names from template."""
        return set(re.findall(r'\{(\w+)}', template))

    @staticmethod
    async def create_counter(
        guild: Guild,
        channel: GuildVoice,
        template: str,
        role_id: Optional[int] = None,
        goal_target: Optional[int] = None,
    ) -> CounterInfo:
        """Create a new counter channel."""
        api = get_api_client()

        # Check if channel already has a counter
        existing = await api.get_counter_by_channel(int(channel.id))
        if existing:
            raise ValueError("This channel already has a counter configured")

        # Determine counter_type for backwards compatibility (use "custom" for new counters)
        counter_type = "custom"

        result = await api.create_counter(
            guild_id=int(guild.id),
            channel_id=int(channel.id),
            counter_type=counter_type,
            template=template,
            role_id=role_id,
            goal_target=goal_target,
        )

        # Get all values and format the channel name
        values = await CounterService.get_all_values(guild, role_id, goal_target)
        formatted = {k: f"{v:,}" for k, v in values.items()}

        try:
            new_name = template.format(**formatted)
            await channel.edit(name=new_name)
            # Store the members value as last_value for tracking changes
            keywords = CounterService._extract_keywords(template)
            primary_value = values.get("members", 0)
            if "role" in keywords:
                primary_value = values.get("role", 0)
            elif "voice" in keywords:
                primary_value = values.get("voice", 0)
            elif "online" in keywords:
                primary_value = values.get("online", 0)
            elif "boosts" in keywords:
                primary_value = values.get("boosts", 0)
            await api.update_counter_value(int(channel.id), primary_value)
        except (Forbidden, NotFound) as e:
            logger.warning(f"Could not update channel name: {e}")
        except KeyError as e:
            logger.warning(f"Missing keyword in template: {e}")

        return CounterInfo(
            id=result["id"],
            guild_id=int(guild.id),
            channel_id=int(channel.id),
            counter_type=counter_type,
            template=template,
            role_id=role_id,
            goal_target=goal_target,
            last_value=values.get("members", 0),
        )

    @staticmethod
    async def get_counter_value(
        guild: Guild,
        counter_type: str,
        role_id: Optional[int] = None,
        goal_target: Optional[int] = None,
    ) -> int:
        """Get the current value for a counter type."""
        if counter_type == "members":
            return guild.member_count or 0

        elif counter_type == "online":
            online = 0
            for presence in  guild.presences:
                # Presences are dicts with 'status' key
                if presence.get('status') in ['online', 'idle', 'dnd']:
                    online += 1
            return online

        elif counter_type == "boosts":
            return guild.premium_subscription_count or 0

        elif counter_type == "role":
            if role_id is None:
                return 0
            count = 0
            if guild.members:
                for member in guild.members:
                    if any(r.id == role_id for r in member.roles):
                        count += 1
            return count

        elif counter_type == "voice":
            api = get_api_client()
            return await api.get_active_voice_count(int(guild.id))

        elif counter_type == "goal":
            return guild.member_count or 0

        return 0

    @staticmethod
    async def remove_counter(channel_id: int) -> bool:
        """Remove a counter from a channel."""
        api = get_api_client()
        return await api.delete_counter(channel_id)

    @staticmethod
    async def get_guild_counters(guild_id: int) -> List[CounterInfo]:
        """Get all counters for a guild."""
        api = get_api_client()
        records = await api.get_guild_counters(guild_id)
        return [
            CounterInfo(
                id=r["id"],
                guild_id=r["guild_id"],
                channel_id=r["channel_id"],
                counter_type=r["counter_type"],
                template=r["template"],
                role_id=r["role_id"],
                goal_target=r["goal_target"],
                last_value=r["last_value"],
            )
            for r in records
        ]

    @staticmethod
    async def update_counter(
        guild: Guild,
        counter: CounterInfo,
    ) -> Optional[int]:
        """Update a counter channel's name. Returns new value if updated."""
        try:
            channel = await guild.fetch_channel(counter.channel_id)
            if not channel:
                return None

            # Get all current values
            values = await CounterService.get_all_values(
                guild,
                counter.role_id,
                counter.goal_target,
            )

            # Format the new channel name with all keyword values
            formatted = {k: f"{v:,}" for k, v in values.items()}

            # For backwards compatibility with old {count} and {goal} templates
            keywords = CounterService._extract_keywords(counter.template)
            if "count" in keywords:
                # Old-style template - determine value based on counter_type
                if counter.counter_type == "role":
                    formatted["count"] = formatted.get("role", "0")
                elif counter.counter_type == "voice":
                    formatted["count"] = formatted.get("voice", "0")
                elif counter.counter_type == "online":
                    formatted["count"] = formatted.get("online", "0")
                elif counter.counter_type == "boosts":
                    formatted["count"] = formatted.get("boosts", "0")
                else:  # members, goal, or unknown
                    formatted["count"] = formatted.get("members", "0")

            try:
                new_name = counter.template.format(**formatted)
            except KeyError as e:
                logger.warning(f"Missing keyword in template for counter {counter.channel_id}: {e}")
                return None

            # Determine primary value for change detection
            if "role" in keywords:
                new_value = values.get("role", 0)
            elif "voice" in keywords:
                new_value = values.get("voice", 0)
            elif "online" in keywords:
                new_value = values.get("online", 0)
            elif "boosts" in keywords:
                new_value = values.get("boosts", 0)
            elif "count" in keywords:
                # Old-style - use counter_type to determine
                if counter.counter_type == "role":
                    new_value = values.get("role", 0)
                elif counter.counter_type == "voice":
                    new_value = values.get("voice", 0)
                elif counter.counter_type == "online":
                    new_value = values.get("online", 0)
                elif counter.counter_type == "boosts":
                    new_value = values.get("boosts", 0)
                else:
                    new_value = values.get("members", 0)
            else:
                new_value = values.get("members", 0)

            # Only update if value changed
            if new_value != counter.last_value:
                await channel.edit(name=new_name)

                api = get_api_client()
                await api.update_counter_value(counter.channel_id, new_value)

                logger.debug(
                    f"Updated counter {counter.channel_id}: {counter.last_value} -> {new_value}"
                )
                return new_value

            return None

        except (Forbidden, NotFound) as e:
            logger.warning(f"Could not update counter {counter.channel_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error updating counter {counter.channel_id}: {e}")
            return None
