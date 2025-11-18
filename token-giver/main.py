import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interactions import Client, Intents, listen
from interactions.api.events import MemberAdd
from bot.env import CLYPPY_SUPPORT_SERVER_ID
from bot.io import get_aiohttp_session
import logging
import asyncio
import sqlite3
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

    async def start(self):
        """Start the bot"""
        token = os.getenv('TOKEN_GIVER_BOT_TOKEN')
        if not token:
            logger.error("TOKEN_GIVER_BOT_TOKEN environment variable not set")
            return

        logger.info("Starting Token Giver Bot...")
        await self.bot.astart(token)


if __name__ == "__main__":
    bot = TokenGiverBot()
    asyncio.run(bot.start())
