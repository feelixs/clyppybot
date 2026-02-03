from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import aiohttp
import json
import base64
from interactions import Embed, Button, ButtonStyle, ActionRow


@dataclass
class ServerRankPaginationState:
    """State for server ranking pagination."""
    message_id: int
    guild_id: str
    time_period: str = "all"
    page: int = 1
    total_pages: int = 1
    user_server_page: int = 1
    entries_per_page: int = 10


class ServerRankPagination:
    """Utilities for server ranking pagination."""

    API_BASE_URL = "https://clyppy.io/api/servers/ranking/"
    CACHE = {}  # Simple in-memory cache: {cache_key: (data, timestamp)}
    CACHE_TTL = 3600  # 1 hour in seconds

    @staticmethod
    async def fetch_ranking_data(guild_id: str, page: int = 1,
                                  time_period: str = "all") -> Dict[str, Any]:
        """
        Fetch server ranking from API with caching.

        Args:
            guild_id: Discord guild/server ID
            page: Page number to fetch
            time_period: Time period filter ('today', 'week', 'month', 'all')

        Returns:
            API response dict with 'success', 'data', 'page', 'total_count', etc.
        """
        import time

        # Check cache first
        cache_key = f"server_ranking_{time_period}_{page}"
        if cache_key in ServerRankPagination.CACHE:
            cached_data, timestamp = ServerRankPagination.CACHE[cache_key]
            if time.time() - timestamp < ServerRankPagination.CACHE_TTL:
                return cached_data

        # Fetch from API
        try:
            params = {
                "page": page,
                "time_period": time_period
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(ServerRankPagination.API_BASE_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Cache the result
                        ServerRankPagination.CACHE[cache_key] = (data, time.time())

                        return data
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
    async def find_server_page(guild_id: str, time_period: str = "all") -> Optional[int]:
        """
        Find which page the server appears on in the ranking.

        Args:
            guild_id: Discord guild/server ID to find
            time_period: Time period filter

        Returns:
            Page number where server appears, or None if not found
        """
        # API returns 100 per page, we display 10 per page
        # So we need to fetch and search through pages

        page = 1
        while True:
            data = await ServerRankPagination.fetch_ranking_data(guild_id, page, time_period)

            if not data.get("success", False):
                return None

            # Search for guild_id in this page's data
            for idx, server in enumerate(data.get("data", [])):
                if server.get("server_id") == guild_id:
                    # Calculate which display page this server is on
                    # API page has 100 entries, we show 10 per page
                    overall_rank = (page - 1) * 100 + idx + 1
                    display_page = (overall_rank + 9) // 10  # Ceiling division
                    return display_page

            # Check if there are more pages
            if not data.get("has_more", False):
                # Server not found in ranking
                return None

            page += 1

            # Safety limit to avoid infinite loops
            if page > 100:
                return None

    @staticmethod
    def create_embed(ranking_data: List[Dict], page: int, total_pages: int,
                     guild_id: str, entries_per_page: int = 10) -> Embed:
        """
        Create Discord embed showing server ranking.

        Args:
            ranking_data: List of server data dicts from API
            page: Current page number
            total_pages: Total number of pages
            guild_id: Current guild ID (to highlight)
            entries_per_page: Number of entries to show per page

        Returns:
            Discord Embed object
        """
        # Determine time period from context (default to "All Time")
        time_period_display = {
            "today": "Today",
            "week": "This Week",
            "month": "This Month",
            "all": "All Time"
        }.get("all", "All Time")  # Default for now, can be passed as param

        # Calculate start rank for this page
        start_rank = (page - 1) * entries_per_page

        # Find current server's rank and data
        current_server_rank = None
        current_server_name = None

        for idx, server in enumerate(ranking_data):
            rank = start_rank + idx + 1
            if server.get("server_id") == guild_id:
                current_server_rank = rank
                current_server_name = server.get("server_name", "Unknown Server")
                break

        # Create embed
        # Use gold color for top 10, blue otherwise
        if current_server_rank and current_server_rank <= 10:
            color = 0xFFD700  # Gold
        else:
            color = 0x5865F2  # Discord Blurple

        embed = Embed(
            title=f"📊 Server Clip Ranking - {time_period_display}",
            color=color
        )

        # Add description with current server info if found
        if current_server_rank and current_server_name:
            embed.description = (
                f"Showing servers ranked by unique clips embedded\n"
                f"Your server: **{current_server_name}** is ranked **#{current_server_rank}**"
            )
        else:
            embed.description = "Showing servers ranked by unique clips embedded"

        # Add field for each server on this page
        for idx, server in enumerate(ranking_data[:entries_per_page]):
            rank = start_rank + idx + 1
            server_name = server.get("server_name", "Unknown Server")
            unique_clips = server.get("unique_clip_count", 0)
            total_embeds = server.get("total_embed_count", 0)
            rate = server.get("embeds_per_hour", 0)

            # Highlight current server
            if server.get("server_id") == guild_id:
                server_name = f"**{server_name}** ⭐"

            # Format the field value
            value = (
                f"🎬 Unique Clips: **{unique_clips:,}**\n"
                f"📊 Total Embeds: **{total_embeds:,}**\n"
                f"⚡ Rate: **{rate:.2f}**/hour"
            )

            embed.add_field(
                name=f"#{rank} - {server_name}",
                value=value,
                inline=False
            )

        # Add footer
        embed.set_footer(text=f"Page {page} of {total_pages} • Updated every hour")

        return embed

    @staticmethod
    def create_buttons(page: int, total_pages: int,
                       state: ServerRankPaginationState) -> List[ActionRow]:
        """
        Create navigation buttons for pagination.

        Args:
            page: Current page number
            total_pages: Total number of pages
            state: Pagination state to encode in button custom_ids

        Returns:
            List of ActionRow components with buttons
        """
        # Encode state as base64 JSON for custom_id
        state_dict = asdict(state)
        state_json = json.dumps(state_dict)
        encoded_state = base64.b64encode(state_json.encode()).decode()

        # Create buttons
        buttons = [
            Button(
                style=ButtonStyle.PRIMARY,
                label="⏮️ First",
                custom_id=f"server_rank_first_{encoded_state}",
                disabled=(page == 1)
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="◀️ Prev",
                custom_id=f"server_rank_prev_{encoded_state}",
                disabled=(page == 1)
            ),
            Button(
                style=ButtonStyle.SECONDARY,
                label=f"Page {page}/{total_pages}",
                custom_id=f"server_rank_page_{encoded_state}",
                disabled=True
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="Next ▶️",
                custom_id=f"server_rank_next_{encoded_state}",
                disabled=(page >= total_pages)
            ),
            Button(
                style=ButtonStyle.PRIMARY,
                label="Last ⏭️",
                custom_id=f"server_rank_last_{encoded_state}",
                disabled=(page >= total_pages)
            ),
        ]

        return [ActionRow(*buttons)]
