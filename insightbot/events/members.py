from interactions import Extension, listen
from interactions.api.events import MemberAdd, MemberRemove, GuildJoin, GuildLeft

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.task_manager import TaskManager

logger = get_logger("insightbot.events.members")


class MemberEvents(Extension):
    """Handle member-related events."""

    @listen(MemberAdd)
    async def on_member_add(self, event: MemberAdd):
        """Track when a member joins a guild."""
        member = event.member

        if not member.guild:
            return

        try:
            guild_id = int(member.guild.id)
            user_id = int(member.id)
            api = get_api_client()

            # 1. Upsert guild membership
            await api.upsert_member(
                guild_id=guild_id,
                user=member.user,
                display_name=member.display_name,
                joined_at=member.joined_at,
                is_bot=member.bot,
            )

            # 3. Log the join event
            await api.log_member_event(guild_id, user_id, "join")

            # 4. Update guild member count
            if member.guild.member_count:
                await api.update_guild_member_count(guild_id, member.guild.member_count)

            logger.debug(f"Member {member.username} joined guild {guild_id}")

        except Exception as e:
            logger.error(f"Error handling member add: {e}")

    @listen(MemberRemove)
    async def on_member_remove(self, event: MemberRemove):
        """Track when a member leaves a guild."""
        member = event.member

        if not member.guild:
            return

        try:
            guild_id = int(member.guild.id)
            user_id = int(member.id)
            api = get_api_client()

            # 1. Upsert global user data (capture latest before they leave)
            await api.upsert_discord_user(
                user=member,
                global_name=getattr(member, 'global_name', None),
            )

            # 2. Log the leave event
            await api.log_member_event(guild_id, user_id, "leave")

            # 3. Remove the member record (but discord_users persists!)
            await api.delete_member(guild_id, user_id)

            # 4. Update guild member count
            if member.guild.member_count:
                await api.update_guild_member_count(guild_id, member.guild.member_count)

            logger.debug(f"Member {member.username} left guild {guild_id}")

        except Exception as e:
            logger.error(f"Error handling member remove: {e}")

    @listen(GuildJoin)
    async def on_guild_join(self, event: GuildJoin):
        """Handle when the bot joins a new guild."""
        guild = event.guild

        try:
            api = get_api_client()

            # Upsert the guild - returns True if this is a new guild
            was_inserted = await api.upsert_guild(
                guild_id=int(guild.id),
                name=guild.name,
                icon_hash=guild.icon.hash if guild.icon else None,
                member_count=guild.member_count or 0,
                boost_level=guild.premium_tier or 0,
                boost_count=guild.premium_subscription_count or 0,
            )

            # Log if it's a new guild (either joined while running, or joined while offline)
            if self.bot.is_ready or was_inserted:
                logger.info(f"Joined guild: {guild.name} ({guild.id})")

            # Sync existing members in bulk
            if guild.members:
                # Prepare discord_users bulk data (global user profiles)
                discord_users_data = [
                    {
                        "user_id": int(member.id),
                        "username": member.username,
                        "global_name": getattr(member, 'global_name', None),
                        "avatar_hash": member.avatar.hash if member.avatar else None,
                    }
                    for member in guild.members
                    if not member.bot
                ]

                # Prepare members bulk data (guild-specific membership)
                members_data = [
                    {
                        "guild_id": int(guild.id),
                        "user_id": int(member.id),
                        "display_name": member.display_name,
                        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                        "is_bot": member.bot,
                    }
                    for member in guild.members
                    if not member.bot
                ]

                if discord_users_data:
                    task_manager = TaskManager.get()
                    # Bulk upsert discord_users first
                    task_manager.create_task(
                        api.bulk_upsert_discord_users(discord_users_data),
                        name="bulk_upsert_discord_users",
                        persist_args=(discord_users_data,),
                    )
                    # Then bulk upsert members
                    task_manager.create_task(
                        api.bulk_upsert_members(members_data, guild),
                        name="bulk_upsert_members",
                        persist_args=(members_data,),
                        persist_kwargs={"guild_id": int(guild.id)},
                    )
        except Exception as e:
            logger.error(f"Error handling guild join: {e}")

    @listen(GuildLeft)
    async def on_guild_left(self, event: GuildLeft):
        """Handle when the bot leaves a guild."""
        guild = event.guild

        if guild:
            logger.info(f"Left guild: {guild.name if hasattr(guild, 'name') else guild.id}")


def setup(bot):
    MemberEvents(bot)
