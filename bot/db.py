import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, Any

logger = logging.getLogger(__name__)


class GuildDatabase:
    def __init__(self, db_path: str = "guild_settings.db"):
        self.db_path = db_path
        self.setup_db()

    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def setup_db(self):
        """Initialize the database with required tables."""
        with self.get_db() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    setting TEXT
                )
            ''')
            conn.commit()

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

    def get_too_large(self, guild_id):
        this_pos = ["trim", "info", "none"]
        s = self.get_setting(guild_id)
        if s is None:
            return this_pos[0]
        this_setting = int(s[0])
        return this_pos[this_setting]

    def get_on_error(self, guild_id):
        on_er = ["info", "none"]
        s = self.get_setting(guild_id)
        if s is None:
            return on_er[0]
        error_setting = int(s[1])
        return on_er[error_setting]

    def set_setting(self, guild_id: int, value: Any) -> bool:
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
