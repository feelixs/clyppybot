"""SQLite-based event queue for batching API calls."""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from ..logging_config import get_logger

logger = get_logger("insightbot.event_queue")

# Event type constants
EVENT_USER_UPSERT = "user_upsert"
EVENT_MESSAGE = "message"
EVENT_VOICE_START = "voice_start"
EVENT_VOICE_END = "voice_end"
EVENT_USER_LAST_ONLINE = "user_last_online"
EVENT_CHANNEL_UPSERT = "channel_upsert"
EVENT_CHANNEL_DELETE = "channel_delete"

# Status constants
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_FAILED = "failed"


class EventQueue:
    """Singleton SQLite-based event queue for batching high-frequency events."""

    _instance: Optional["EventQueue"] = None
    _db_path: Path = Path(__file__).parent.parent / "data" / "event_queue.db"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the event queue (singleton pattern)."""
        if self._initialized:
            return
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = True

    async def _get_db(self) -> aiosqlite.Connection:
        """Get or create the database connection."""
        if self._db is None:
            # Ensure data directory exists
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

            self._db = await aiosqlite.connect(str(self._db_path))
            self._db.row_factory = aiosqlite.Row

            # Create table and index
            await self._db.execute("""
                                   CREATE TABLE IF NOT EXISTS event_queue (
                                                                              id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                              event_type TEXT NOT NULL,
                                                                              payload TEXT NOT NULL,
                                                                              created_at TEXT NOT NULL,
                                                                              status TEXT NOT NULL DEFAULT 'pending',
                                                                              retry_count INTEGER NOT NULL DEFAULT 0,
                                                                              last_error TEXT
                                   )
                                   """)

            await self._db.execute("""
                                   CREATE INDEX IF NOT EXISTS idx_queue_status_type_created
                                       ON event_queue (status, event_type, created_at)
                                   """)

            await self._db.commit()
            logger.info(f"Event queue initialized at {self._db_path}")

        return self._db

    async def enqueue(self, event_type: str, payload: dict) -> None:
        """
        Enqueue an event for later batch processing.

        Args:
            event_type: Type of event (user_upsert, message, voice_start, voice_end)
            payload: Event data as a dictionary
        """
        db = await self._get_db()

        try:
            await db.execute(
                """
                INSERT INTO event_queue (event_type, payload, created_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event_type,
                    json.dumps(payload),
                    datetime.utcnow().isoformat(),
                    STATUS_PENDING,
                ),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to enqueue {event_type} event: {e}")
            raise

    async def fetch_batch(self, event_type: str, limit: int = 100) -> List[Dict]:
        """
        Fetch a batch of pending events and mark them as processing.

        Args:
            event_type: Type of event to fetch
            limit: Maximum number of events to fetch

        Returns:
            List of event dictionaries with id, event_type, payload (parsed JSON)
        """
        db = await self._get_db()

        try:
            # Fetch pending events
            cursor = await db.execute(
                """
                SELECT id, event_type, payload, created_at
                FROM event_queue
                WHERE status = ? AND event_type = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (STATUS_PENDING, event_type, limit),
            )

            rows = await cursor.fetchall()

            if not rows:
                return []

            # Mark as processing
            event_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(event_ids))
            await db.execute(
                f"""
                UPDATE event_queue
                SET status = ?
                WHERE id IN ({placeholders})
                """,
                [STATUS_PROCESSING] + event_ids,
                )
            await db.commit()

            # Parse and return events
            events = []
            for row in rows:
                events.append({
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"]),
                    "created_at": row["created_at"],
                })

            return events

        except Exception as e:
            logger.error(f"Failed to fetch batch for {event_type}: {e}")
            raise

    async def mark_processed(self, event_ids: List[int]) -> None:
        """
        Delete successfully processed events from the queue.

        Args:
            event_ids: List of event IDs to delete
        """
        if not event_ids:
            return

        db = await self._get_db()

        try:
            placeholders = ",".join("?" * len(event_ids))
            await db.execute(
                f"DELETE FROM event_queue WHERE id IN ({placeholders})",
                event_ids,
            )
            await db.commit()
            logger.debug(f"Marked {len(event_ids)} events as processed and deleted")
        except Exception as e:
            logger.error(f"Failed to mark events as processed: {e}")
            raise

    async def mark_failed(self, event_ids: List[int], error: str) -> None:
        """
        Mark events as failed and reset to pending for retry.

        Args:
            event_ids: List of event IDs that failed
            error: Error message to store
        """
        if not event_ids:
            return

        db = await self._get_db()

        try:
            placeholders = ",".join("?" * len(event_ids))
            await db.execute(
                f"""
                UPDATE event_queue
                SET status = ?, retry_count = retry_count + 1, last_error = ?
                WHERE id IN ({placeholders})
                """,
                [STATUS_PENDING, error] + event_ids,
                )
            await db.commit()
            logger.warning(f"Marked {len(event_ids)} events as failed for retry: {error}")
        except Exception as e:
            logger.error(f"Failed to mark events as failed: {e}")
            raise

    async def get_queue_depth(self) -> Dict[str, int]:
        """
        Get the count of pending events by type.

        Returns:
            Dictionary mapping event_type to count of pending events
        """
        db = await self._get_db()

        try:
            cursor = await db.execute(
                """
                SELECT event_type, COUNT(*) as count
                FROM event_queue
                WHERE status = ?
                GROUP BY event_type
                """,
                (STATUS_PENDING,),
            )

            rows = await cursor.fetchall()
            return {row["event_type"]: row["count"] for row in rows}

        except Exception as e:
            logger.error(f"Failed to get queue depth: {e}")
            return {}

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("Event queue connection closed")


# Global queue instance
_queue: Optional[EventQueue] = None


def get_event_queue() -> EventQueue:
    """Get the global event queue instance."""
    global _queue
    if _queue is None:
        _queue = EventQueue()
    return _queue


async def close_event_queue() -> None:
    """Close the global event queue."""
    global _queue
    if _queue is not None:
        await _queue.close()
        _queue = None
