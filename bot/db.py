import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, Any, Callable

logger = logging.getLogger(__name__)

possible_too_large = ["trim", "info", "none"]
possible_on_err = ["info", "none"]


class GuildDatabase:
    def __init__(self, db_path: str = "guild_settings.db", on_save: Callable = None, on_load: Callable = None):
        self.db_path = db_path
        self.on_save = on_save
        self.on_load = on_load
        self.setup_db()

    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    async def setup_db(self):
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
            await self.on_load()

    def get_setting(self, guild_id: int) -> Optional[str]:
        try:
            with self.get_db() as conn:
                cursor = conn.execute(
                    'SELECT setting FROM guild_settings WHERE guild_id = ?',
                    (guild_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Database error when getting setting for guild {guild_id}: {e}")
            return None

    def get_setting_str(self, guild_id):
        sett = self.get_setting(guild_id)

        # translate to words
        if sett is None:
            settings = possible_too_large[0], possible_on_err[0]
        else:
            settings = possible_too_large[int(sett[0])], possible_on_err[int(sett[1])]
        return (f"**too_large**: {settings[0]}\n\n"
                f"**on_error**: {settings[1]}")

    def get_too_large(self, guild_id):
        this_pos = possible_too_large
        s = self.get_setting(guild_id)
        if s is None:
            return this_pos[0]
        this_setting = int(s[0])
        return this_pos[this_setting]

    def get_on_error(self, guild_id):
        on_er = possible_on_err
        s = self.get_setting(guild_id)
        if s is None:
            return on_er[0]
        error_setting = int(s[1])
        return on_er[error_setting]

    async def set_setting(self, guild_id: int, value: Any) -> bool:
        """Set or update setting for a specific guild."""
        try:
            with self.get_db() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO guild_settings (guild_id, setting)
                    VALUES (?, ?)
                ''', (guild_id, str(value)))
                conn.commit()

                # Call the save callback if it exists
                if self.on_save:
                    await self.on_save(guild_id, value)
                return True
        except sqlite3.Error as e:
            logger.error(f"Database error when setting value for guild {guild_id}: {e}")
            return False
