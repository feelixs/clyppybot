import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interactions import Client, Intents, listen, Task, IntervalTrigger
from interactions.api.events import MemberAdd
from bot.env import CLYPPY_SUPPORT_SERVER_ID, is_contrib_instance, log_api_bypass
from bot.io import get_aiohttp_session
import logging
import asyncio
import sqlite3
import re
from datetime import datetime
from os import getenv


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TokenGiverBot:
    def __init__(self):
        self.bot = Client(intents=Intents.DEFAULT | Intents.GUILD_MEMBERS)
        # Use environment variable or default to data directory for persistence
        self.db_path = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'data', 'members.db'))
        self.setup_database()
        self.setup_listeners()

    def setup_database(self):
        """Initialize SQLite database for tracking token grants"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS token_grants (
                user_id INTEGER PRIMARY KEY,
                granted_at TIMESTAMP NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def setup_listeners(self):
        """Setup event listeners"""

        @listen(MemberAdd)
        async def on_member_add(event: MemberAdd):
            # Validate this is the correct server
            if event.guild.id != CLYPPY_SUPPORT_SERVER_ID:
                return

            logger.info(f"New member joined {event.guild.name}: {event.member.username} (ID: {event.member.id})")

            # Check if user already received tokens
            if self.has_received_tokens(event.member.id):
                logger.info(f"User {event.member.id} already received tokens previously")
                return

            try:
                # Call the token giving function
                await self.give_tokens_to_user(event.member, 4)

                # Record the successful token grant
                self.record_token_grant(event.member.id)
                logger.info(f"Successfully gave 4 tokens to {event.member.username} (ID: {event.member.id})")

            except Exception as e:
                logger.error(f"Error giving tokens to {event.member.id}: {e}")

        self.bot.add_listener(on_member_add)

    def has_received_tokens(self, user_id: int) -> bool:
        """Check if user has already received tokens"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM token_grants WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def record_token_grant(self, user_id: int):
        """Record that a user received tokens"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO token_grants (user_id, granted_at) VALUES (?, ?)',
            (user_id, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    async def give_tokens_to_user(self, member, amount: int):
        """
        Give tokens to a user by calling the clyppy.io API.

        Args:
            member: Discord Member object
            amount: Number of tokens to give

        Uses the subtract API with a negative amount to add tokens.
        """
        if is_contrib_instance():
            log_api_bypass(__name__, "https://clyppy.io/api/tokens/subtract/", "POST", {
                "user_id": member.id,
                "amount": -amount,
                "reason": "New Member Bonus"
            })
            logger.info(f"[CONTRIB MODE] Would give {amount} tokens to {member.username}")
            return {"success": True, "user_success": True, "tokens": 999}

        url = 'https://clyppy.io/api/tokens/subtract/'
        headers = {
            'X-API-Key': getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        payload = {
            'userid': member.id,
            'username': member.username,
            'amount': -amount,  # Negative to add tokens
            'reason': 'New Member Bonus',
            'description': f'Welcome bonus for joining CLYPPY CLUB',
        }

        async with get_aiohttp_session() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Successfully gave {amount} tokens to {member.username}. API response: {result}")
                    return result
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to give VIP tokens: {error_data.get('error', 'Unknown error')}")

    async def cleanup_vote_roles_for_member(self, member):
        """
        Remove redundant vote roles from a member, keeping only the highest.

        Finds all roles matching 'X Votes' pattern, determines the max X,
        and removes all vote roles with X less than the max.
        """
        vote_role_pattern = re.compile(r'^(\d+)\s+Votes?$')
        vote_roles = []

        for role in member.roles:
            match = vote_role_pattern.match(role.name)
            if match:
                vote_count = int(match.group(1))
                vote_roles.append((vote_count, role))

        if len(vote_roles) <= 1:
            return 0

        max_votes = max(vote_count for vote_count, _ in vote_roles)
        roles_to_remove = [role for vote_count, role in vote_roles if vote_count < max_votes]

        removed_count = 0
        for role in roles_to_remove:
            try:
                await member.remove_role(role)
                removed_count += 1
                logger.info(f"Removed role '{role.name}' from {member.username} (ID: {member.id})")
            except Exception as e:
                logger.error(f"Failed to remove role '{role.name}' from {member.id}: {e}")

        return removed_count

    async def cleanup_all_vote_roles(self):
        """
        Clean up vote roles for all members in the support server.
        """
        logger.info("Starting vote role cleanup task...")

        guild = self.bot.get_guild(CLYPPY_SUPPORT_SERVER_ID)
        if not guild:
            logger.error(f"Could not find guild with ID {CLYPPY_SUPPORT_SERVER_ID}")
            return

        await guild.chunk()

        total_removed = 0
        members_processed = 0

        for member in guild.members:
            removed = await self.cleanup_vote_roles_for_member(member)
            total_removed += removed
            members_processed += 1

        logger.info(f"Vote role cleanup complete. Processed {members_processed} members, removed {total_removed} redundant vote roles.")

    def setup_tasks(self):
        """Setup background tasks"""
        @Task.create(IntervalTrigger(hours=24))
        async def vote_role_cleanup_task():
            await self.cleanup_all_vote_roles()

        self.vote_role_cleanup_task = vote_role_cleanup_task

    async def start(self):
        """Start the bot"""
        token = os.getenv('TOKEN_GIVER_BOT_TOKEN')
        if not token:
            logger.error("TOKEN_GIVER_BOT_TOKEN environment variable not set")
            return

        self.setup_tasks()

        @listen()
        async def on_ready():
            logger.info("Bot is ready, running initial vote role cleanup...")
            await self.cleanup_all_vote_roles()
            self.vote_role_cleanup_task.start()
            logger.info("Vote role cleanup task scheduled to run every 24 hours")

        self.bot.add_listener(on_ready)

        logger.info("Starting Token Giver Bot...")
        await self.bot.astart(token)


if __name__ == "__main__":
    bot = TokenGiverBot()
    asyncio.run(bot.start())
