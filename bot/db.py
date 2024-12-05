import sqlite3
import logging
from contextlib import contextmanager
from typing import Any, Callable
from bot.tools import POSSIBLE_TOO_LARGE, POSSIBLE_ON_ERRORS


logger = logging.getLogger(__name__)


class DbResponseFormat:
    def __init__(self, possible_values: [str], stored_int: int):
        self.all_values = possible_values
        self.id = stored_int
        self.setting_str = possible_values[self.id]

    def __str__(self):
        return self.setting_str


class GuildDatabase:
    def __init__(self, db_path: str = "guild_settings.db", on_save: Callable = None, on_load: Callable = None):
        self.db_path = db_path
        self.on_save = on_save
        self.on_load = on_load

    async def save(self):
        """Save database to server if callback exists."""
        if self.on_save:
            logger.info("Saving database to the server...")
            await self.on_save()

    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    async def setup_db(self):
        logger.info("Setting up database...")
        """Initialize the database with required tables and load from server."""
        with self.get_db() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    setting TEXT
                )
            ''')
            conn.commit()

        # Load from server if callback exists
        if self.on_load:
            logger.info("Loading database from the server...")
            await self.on_load()

    def get_setting(self, guild_id: int) -> str:
        try:
            with self.get_db() as conn:
                cursor = conn.execute(
                    'SELECT setting FROM guild_settings WHERE guild_id = ?',
                    (guild_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else "00"
        except sqlite3.Error as e:
            logger.error(f"Database error when getting setting for guild {guild_id}: {e}")
            return "00"

    def get_setting_str(self, guild_id):
        sett = self.get_setting(guild_id)

        # translate to words
        if sett is None:
            settings = POSSIBLE_TOO_LARGE[0], POSSIBLE_ON_ERRORS[0]
        else:
            settings = POSSIBLE_TOO_LARGE[int(sett[0])], POSSIBLE_ON_ERRORS[int(sett[1])]
        return (f"**too_large**: {settings[0]}\n"
                f"**on_error**: {settings[1]}")

    def get_too_large(self, guild_id) -> DbResponseFormat:
        this_pos = POSSIBLE_TOO_LARGE
        s = self.get_setting(guild_id)
        if s is None:
            return this_pos[0]
        this_setting = int(s[0])
        return DbResponseFormat(POSSIBLE_TOO_LARGE, this_setting)

    def get_on_error(self, guild_id) -> DbResponseFormat:
        on_er = POSSIBLE_ON_ERRORS
        s = self.get_setting(guild_id)
        if s is None:
            return on_er[0]
        error_setting = int(s[1])
        return DbResponseFormat(POSSIBLE_ON_ERRORS, error_setting)

    async def set_setting(self, guild_id: int, value: Any) -> bool:
        """Set or update setting for a specific guild."""
        try:
            with self.get_db() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO guild_settings (guild_id, setting)
                    VALUES (?, ?)
                ''', (guild_id, str(value)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Database error when setting value for guild {guild_id}: {e}")
            return False
