"""Invite tracking for attribution.

Tracks which invites are used when members join to attribute who invited whom.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from interactions import Extension, listen
from interactions.api.events import MemberAdd, GuildJoin, Ready

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.events.invite_tracker")


@dataclass
class CachedInvite:
    """Cached invite data for comparison."""

    code: str
    inviter_id: Optional[int]
    uses: int
    max_uses: Optional[int]


class InviteTracker(Extension):
    """Tracks invite usage to attribute member joins."""

    def __init__(self, bot):
        self.bot = bot
        # guild_id -> {invite_code -> CachedInvite}
        self._invite_cache: Dict[int, Dict[str, CachedInvite]] = {}

    def _has_manage_guild_permission(self, guild) -> bool:
        """Check if the bot has MANAGE_GUILD permission in the guild."""
        from interactions import Permissions
        try:
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                return False
            return bot_member.has_permission(Permissions.MANAGE_GUILD)
        except Exception as e:
            logger.debug(f"Guild {guild.id}: permission check error: {e}")
            return False

    async def _cache_guild_invites(self, guild) -> bool:
        """Cache all invites for a guild. Returns True if successful."""
        guild_id = int(guild.id)

        # Check permission before attempting to fetch
        if not self._has_manage_guild_permission(guild):
            logger.debug(f"Skipping invite cache for guild {guild_id}: missing MANAGE_GUILD permission")
            return False

        try:
            # Fetch all invites for the guild
            invites = await guild.fetch_invites()

            self._invite_cache[guild_id] = {}
            for invite in invites:
                inviter_id = int(invite.inviter.id) if invite.inviter else None
                self._invite_cache[guild_id][invite.code] = CachedInvite(
                    code=invite.code,
                    inviter_id=inviter_id,
                    uses=invite.uses or 0,
                    max_uses=invite.max_uses,
                )

            logger.debug(
                f"Cached {len(self._invite_cache[guild_id])} invites for guild {guild_id}"
            )
            return True

        except Exception as e:
            # Bot may not have permission to fetch invites
            logger.warning(f"Could not cache invites for guild {guild_id}: {e}")
            return False

    async def _find_used_invite(self, guild) -> Optional[CachedInvite]:
        """Compare cached invites to current invites to find which was used."""
        guild_id = int(guild.id)
        old_cache = self._invite_cache.get(guild_id, {})

        # Check permission before attempting to fetch
        if not self._has_manage_guild_permission(guild):
            return None

        try:
            # Fetch current invites
            current_invites = await guild.fetch_invites()
            current_map = {inv.code: inv for inv in current_invites}

            # Find invite with increased uses
            for code, cached in old_cache.items():
                current = current_map.get(code)
                if current and current.uses > cached.uses:
                    # This invite was used
                    used_invite = CachedInvite(
                        code=cached.code,
                        inviter_id=cached.inviter_id,
                        uses=current.uses,
                        max_uses=cached.max_uses,
                    )

                    # Update cache with new values
                    self._invite_cache[guild_id] = {}
                    for inv in current_invites:
                        inviter_id = int(inv.inviter.id) if inv.inviter else None
                        self._invite_cache[guild_id][inv.code] = CachedInvite(
                            code=inv.code,
                            inviter_id=inviter_id,
                            uses=inv.uses or 0,
                            max_uses=inv.max_uses,
                        )

                    return used_invite

            # Check for invite that was deleted (hit max uses)
            for code, cached in old_cache.items():
                if code not in current_map:
                    # Invite was deleted, might have hit max uses
                    if cached.max_uses and cached.uses + 1 >= cached.max_uses:
                        # Update cache
                        self._invite_cache[guild_id] = {}
                        for inv in current_invites:
                            inviter_id = int(inv.inviter.id) if inv.inviter else None
                            self._invite_cache[guild_id][inv.code] = CachedInvite(
                                code=inv.code,
                                inviter_id=inviter_id,
                                uses=inv.uses or 0,
                                max_uses=inv.max_uses,
                            )
                        return cached

            # Update cache even if we didn't find the invite
            self._invite_cache[guild_id] = {}
            for inv in current_invites:
                inviter_id = int(inv.inviter.id) if inv.inviter else None
                self._invite_cache[guild_id][inv.code] = CachedInvite(
                    code=inv.code,
                    inviter_id=inviter_id,
                    uses=inv.uses or 0,
                    max_uses=inv.max_uses,
                )

            return None

        except Exception as e:
            logger.warning(f"Could not compare invites for guild {guild_id}: {e}")
            return None

    @listen(Ready)
    async def on_ready(self):
        """Cache invites for all guilds on bot ready."""
        logger.info("Caching invites for all guilds...")
        cached_count = 0
        failed_count = 0

        for guild in self.bot.guilds:
            if await self._cache_guild_invites(guild):
                cached_count += 1
            else:
                failed_count += 1

        logger.info(
            f"Invite caching complete: {cached_count} guilds cached, "
            f"{failed_count} failed (missing permissions)"
        )

    @listen(GuildJoin)
    async def on_guild_join(self, event: GuildJoin):
        """Cache invites when bot joins a new guild."""
        guild = event.guild
        await self._cache_guild_invites(guild)

    @listen(MemberAdd)
    async def on_member_add(self, event: MemberAdd):
        """Track which invite was used when a member joins."""
        member = event.member

        if not member.guild or member.bot:
            return

        guild_id = int(member.guild.id)
        member_id = int(member.id)

        try:
            # Find which invite was used
            used_invite = await self._find_used_invite(member.guild)

            # Record the invite attribution
            api = get_api_client()

            if used_invite:
                await api.record_member_invite(
                    guild_id=guild_id,
                    member_id=member_id,
                    invited_by_id=used_invite.inviter_id,
                    invite_code=used_invite.code,
                    joined_at=member.joined_at or datetime.now(timezone.utc),
                )
                logger.debug(
                    f"Member {member_id} joined guild {guild_id} via invite "
                    f"{used_invite.code} from user {used_invite.inviter_id}"
                )
            else:
                # Record join without invite attribution (vanity URL, discovery, etc.)
                await api.record_member_invite(
                    guild_id=guild_id,
                    member_id=member_id,
                    invited_by_id=None,
                    invite_code=None,
                    joined_at=member.joined_at or datetime.now(timezone.utc),
                )
                logger.debug(
                    f"Member {member_id} joined guild {guild_id} (invite unknown)"
                )

        except Exception as e:
            logger.error(f"Error tracking invite for member {member_id}: {e}")


def setup(bot):
    InviteTracker(bot)
