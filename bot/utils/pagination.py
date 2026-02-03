from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import aiohttp
import time
from os import getenv
from interactions import Embed, Button, ButtonStyle, ActionRow
from bot.env import CLYPPYIO_USER_AGENT

ENTRIES_PER_PAGE = 5


@dataclass
class UserRankPaginationState:
    """State for user ranking pagination."""
    user_id: str
    time_period: str = "all"
    page: int = 1
    total_pages: int = 1


class UserRankPagination:
    """Utilities for user ranking pagination."""

    API_BASE_URL = "https://clyppy.io/api/users/ranking/"

    @staticmethod
    async def fetch_ranking_data(page: int = 1, time_period: str = "all") -> Dict[str, Any]:
        """
        Fetch user ranking from API.

        Args:
            page: Page number to fetch
            time_period: Time period filter ('today', 'week', 'month', 'all')

        Returns:
            API response dict with 'success', 'data', 'page', 'total_count', etc.
        """
        try:
            params = {
                "page": page,
                "per_page": ENTRIES_PER_PAGE,
                "time_period": time_period
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(UserRankPagination.API_BASE_URL, params=params, headers={
                    "User-Agent": CLYPPYIO_USER_AGENT,
                    'X-API-Key': getenv('clyppy_post_key'),
                    'Content-Type': 'application/json'
                }) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {
                            "success": False,
                            "error": f"API returned status {response.status}"
                        }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    async def find_user_page(user_id: str, time_period: str = "all") -> Optional[int]:
        """
        Find which page the user appears on in the ranking.

        Args:
            user_id: Discord user ID to find
            time_period: Time period filter

        Returns:
            Page number where user appears, or None if not found
        """
        page = 1
        while True:
            data = await UserRankPagination.fetch_ranking_data(page, time_period)

            if not data.get("success", False):
                return None

            # Search for user_id in this page's data
            for user in data.get("data", []):
                if str(user.get("user_id")) == str(user_id):
                    return page

            # Check if there are more pages
            if not data.get("has_more", False):
                return None

            page += 1

            # Safety limit
            if page > 1000:
                return None

    @staticmethod
    def create_embed(ranking_data: List[Dict], page: int, total_pages: int,
                     user_id: str, time_period: str = "all") -> Embed:
        """Create Discord embed showing user ranking."""
        time_period_display = {
            "today": "Today",
            "week": "This Week",
            "month": "This Month",
            "all": "All Time"
        }.get(time_period, "All Time")

        # Calculate start rank for this page
        start_rank = (page - 1) * ENTRIES_PER_PAGE

        # Find target user's rank
        target_user_rank = None
        target_user_name = None

        for idx, user in enumerate(ranking_data):
            if str(user.get("user_id")) == str(user_id):
                target_user_rank = start_rank + idx + 1
                target_user_name = user.get("user_name", "Unknown User")
                break

        # Gold for top 10, blue otherwise
        color = 0xFFD700 if target_user_rank and target_user_rank <= 10 else 0x5865F2

        embed = Embed(
            title=f"📊 User Clip Ranking - {time_period_display}",
            color=color
        )

        if target_user_rank and target_user_name:
            embed.description = (
                f"Showing users ranked by unique clips embedded\n"
                f"**{target_user_name}** is ranked **#{target_user_rank}**"
            )
        else:
            embed.description = "Showing users ranked by unique clips embedded"

        # Add field for each user
        for idx, user in enumerate(ranking_data):
            rank = start_rank + idx + 1
            user_name = user.get("user_name", "Unknown User")
            unique_clips = user.get("unique_clip_count", 0)
            total_embeds = user.get("total_embed_count", 0)
            servers_used = user.get("servers_used", 0)

            # Highlight target user
            if str(user.get("user_id")) == str(user_id):
                user_name = f"**{user_name}** ⭐"

            value = (
                f"🎬 Unique Clips: **{unique_clips:,}**\n"
                f"📊 Total Embeds: **{total_embeds:,}**\n"
                f"🌐 Servers: **{servers_used}**"
            )

            embed.add_field(
                name=f"#{rank} - {user_name}",
                value=value,
                inline=False
            )

        embed.set_footer(text=f"Page {page} of {total_pages} • Updated every hour")
        return embed

    @staticmethod
    def create_buttons(page: int, total_pages: int, state: UserRankPaginationState) -> List[ActionRow]:
        """Create navigation buttons for pagination."""
        # Compact format: ur_{action}_{user_id}_{tp}_{page}_{total}_{ts}
        tp_code = {"all": "a", "week": "w", "month": "m", "today": "t"}.get(state.time_period, "a")
        ts = str(int(time.time() * 1000) % 100000)

        buttons = [
            Button(
                style=ButtonStyle.PRIMARY,
                label="⏮️ First",
                custom_id=f"ur_f_{state.user_id}_{tp_code}_{page}_{total_pages}_{ts}",
                disabled=(page == 1)
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="◀️ Prev",
                custom_id=f"ur_p_{state.user_id}_{tp_code}_{page}_{total_pages}_{ts}",
                disabled=(page == 1)
            ),
            Button(
                style=ButtonStyle.SECONDARY,
                label=f"Page {page}/{total_pages}",
                custom_id=f"ur_x_{state.user_id}_{tp_code}_{page}_{total_pages}_{ts}",
                disabled=True
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="Next ▶️",
                custom_id=f"ur_n_{state.user_id}_{tp_code}_{page}_{total_pages}_{ts}",
                disabled=(page >= total_pages)
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="Last ⏭️",
                custom_id=f"ur_l_{state.user_id}_{tp_code}_{page}_{total_pages}_{ts}",
                disabled=(page >= total_pages)
            ),
        ]

        return [ActionRow(*buttons)]
