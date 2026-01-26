import asyncio

from interactions import Extension, listen
from interactions.api.events import MemberAdd, MemberRemove, GuildJoin, GuildLeft, RoleCreate, RoleUpdate, RoleDelete, MemberUpdate

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.task_manager import TaskManager
from ..services.event_queue import get_event_queue, EVENT_USER_LAST_ONLINE
from .. import intent_flags

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

            # Sync existing members in bulk (only if GUILD_MEMBERS intent is available)
            if intent_flags.HAS_GUILD_MEMBERS and guild.members:
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
                    # discord_users must complete before members (FK constraint)
                    await api.bulk_upsert_discord_users(discord_users_data)
                    # Members can run as background task now
                    members_task = task_manager.create_task(
                        api.bulk_upsert_members(members_data, guild),
                        name="bulk_upsert_members",
                        persist_args=(members_data,),
                        persist_kwargs={"guild_id": int(guild.id)},
                    )

                    # Capture initial presence states for online users (only if GUILD_PRESENCES is available)
                    if intent_flags.HAS_GUILD_PRESENCES:
                        queue = get_event_queue()
                        online_count = 0
                        for member in guild.members:
                            if not member.bot and member.status and str(member.status) in ['online', 'idle', 'dnd']:
                                await queue.enqueue(EVENT_USER_LAST_ONLINE, {
                                    "user_id": int(member.id),
                                })
                                online_count += 1

                        if online_count > 0:
                            logger.info(f"Queued {online_count} initial presence states for guild {guild.id}")
                else:
                    members_task = None

            # Sync roles in bulk
            roles_task = None
            if guild.roles:
                task_manager = TaskManager.get()
                roles_data = [
                    {
                        "role_id": int(role.id),
                        "guild_id": int(guild.id),
                        "name": role.name,
                        "color": role.color.value if role.color else None,
                        "position": role.position,
                        "is_hoisted": role.hoist,
                        "is_mentionable": role.mentionable,
                        "is_managed": role.managed,
                    }
                    for role in guild.roles
                    if not role.default  # Skip @everyone
                ]
                if roles_data:
                    roles_task = task_manager.create_task(
                        api.bulk_upsert_roles(roles_data),
                        name="bulk_upsert_roles",
                        persist_args=(roles_data,),
                    )

                # Sync member roles - must wait for members and roles to complete (FK constraints)
                member_roles_data = [
                    {
                        "user_id": int(member.id),
                        "role_ids": [int(r.id) for r in member.roles if not r.default]
                    }
                    for member in guild.members
                    if not member.bot
                ]
                if member_roles_data:
                    # Wait for prerequisite tasks before syncing member_roles
                    tasks_to_await = [t for t in [members_task, roles_task] if t]
                    if tasks_to_await:
                        await asyncio.gather(*tasks_to_await)
                    task_manager.create_task(
                        api.bulk_sync_member_roles(int(guild.id), member_roles_data),
                        name="bulk_sync_member_roles",
                        persist_args=(int(guild.id), member_roles_data),
                    )

        except Exception as e:
            logger.error(f"Error handling guild join: {e}")

    @listen(GuildLeft)
    async def on_guild_left(self, event: GuildLeft):
        """Handle when the bot leaves a guild."""
        guild = event.guild

        if guild:
            logger.info(f"Left guild: {guild.name if hasattr(guild, 'name') else guild.id}")

    @listen(RoleCreate)
    async def on_role_create(self, event: RoleCreate):
        """Handle when a role is created."""
        role = event.role

        try:
            api = get_api_client()
            await api.upsert_role(
                role_id=int(role.id),
                guild_id=int(role.guild.id),
                name=role.name,
                color=role.color.value if role.color else None,
                position=role.position,
                is_hoisted=role.hoist,
                is_mentionable=role.mentionable,
                is_managed=role.managed,
            )
            logger.debug(f"Role created: {role.name} in guild {role.guild.id}")
        except Exception as e:
            logger.error(f"Error handling role create: {e}")

    @listen(RoleUpdate)
    async def on_role_update(self, event: RoleUpdate):
        """Handle when a role is updated."""
        role = event.role

        try:
            api = get_api_client()
            await api.upsert_role(
                role_id=int(role.id),
                guild_id=int(role.guild.id),
                name=role.name,
                color=role.color.value if role.color else None,
                position=role.position,
                is_hoisted=role.hoist,
                is_mentionable=role.mentionable,
                is_managed=role.managed,
            )
            logger.debug(f"Role updated: {role.name} in guild {role.guild.id}")
        except Exception as e:
            logger.error(f"Error handling role update: {e}")

    @listen(RoleDelete)
    async def on_role_delete(self, event: RoleDelete):
        """Handle when a role is deleted."""
        try:
            api = get_api_client()
            await api.delete_role(int(event.role_id))
            logger.debug(f"Role deleted: {event.role_id}")
        except Exception as e:
            logger.error(f"Error handling role delete: {e}")

    @listen(MemberUpdate)
    async def on_member_update(self, event: MemberUpdate):
        """Handle when a member is updated (including role changes)."""
        before = event.before
        after = event.after

        # Only sync if roles changed
        if before and after and before.roles != after.roles:
            try:
                api = get_api_client()
                role_ids = [int(r.id) for r in after.roles if not r.default]
                await api.sync_member_roles(
                    guild_id=int(after.guild.id),
                    user_id=int(after.id),
                    role_ids=role_ids,
                )
                logger.debug(f"Member roles updated: {after.id} in guild {after.guild.id}")
            except Exception as e:
                logger.error(f"Error handling member role update: {e}")


def setup(bot):
    MemberEvents(bot)
