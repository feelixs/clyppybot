"""Analytics collector for time-series data.

Collects Discord events and aggregates them for hourly submission to the API.
Includes topic tracking for AI insights with tier-based matching.
"""

import pickle
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path
from threading import Lock
from typing import Dict, Set, Optional, List

from interactions import Extension, Task, IntervalTrigger, listen
from interactions.api.events import (
    MessageCreate,
    VoiceStateUpdate,
    MemberAdd,
    MemberRemove,
    Startup,
)

from ..api_client import get_api_client
from ..logging_config import get_logger

logger = get_logger("insightbot.events.analytics_collector")

# Minimum/maximum word length for unknown word tracking
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 16  # Avoid tracking URLs and very long strings

# Word frequency tracking for phrase correlation detection
# Only submit words with 10+ mentions per guild (aggressive filtering)
FREQ_MIN_MENTIONS = 10

# Regex pattern for extracting words (supports Unicode for multilingual)
WORD_PATTERN = re.compile(r'[\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uac00-\ud7af]+', re.UNICODE)

# Pickle file path for persisting analytics data across restarts
ANALYTICS_PICKLE_PATH = Path(__file__).parent.parent / "data" / "analytics_state.pkl"


@dataclass
class CachedTopicAlias:
    """Cached topic alias with tier-based matching metadata."""

    topic_id: int
    category_id: int
    is_anchor: bool
    is_ambiguous: bool
    full_phrase: Optional[str]


@dataclass
class GuildStats:
    """Accumulated stats for a guild during the current hour."""

    messages: int = 0
    voice_minutes: int = 0
    active_users: Set[int] = field(default_factory=set)
    members_joined: int = 0
    members_left: int = 0


@dataclass
class ChannelStats:
    """Accumulated stats for a channel during the current hour."""

    messages: int = 0
    active_users: Set[int] = field(default_factory=set)


@dataclass
class VoiceSession:
    """Tracks an active voice session for minutes calculation."""

    guild_id: int
    channel_id: int
    user_id: int
    started_at: datetime


@dataclass
class TopicMentionStats:
    """Accumulated stats for a topic mention in a channel."""

    mention_count: int = 0
    user_ids: Set[int] = field(default_factory=set)


@dataclass
class UnknownWordStats:
    """Accumulated stats for an unknown word in a guild."""

    mention_count: int = 0
    user_ids: Set[int] = field(default_factory=set)


@dataclass
class WordFrequencyStats:
    """Accumulated word frequency for phrase correlation detection."""

    mention_count: int = 0


class AnalyticsCollector(Extension):
    """Collects Discord events and submits hourly analytics."""

    def __init__(self, bot):
        self.bot = bot
        self._lock = Lock()

        # In-memory counters reset each hour
        self._guild_stats: Dict[int, GuildStats] = defaultdict(GuildStats)
        self._channel_stats: Dict[tuple[int, int], ChannelStats] = defaultdict(
            ChannelStats
        )

        # Track active voice sessions for minutes calculation
        self._voice_sessions: Dict[tuple[int, int], VoiceSession] = {}

        # Track the current hour bucket
        self._current_hour: datetime = self._get_hour_bucket()

        # Topic tracking with tier-based matching
        # alias (lowercase) -> CachedTopicAlias
        self._topic_aliases: Dict[str, CachedTopicAlias] = {}
        # category_id -> set of context words
        self._context_words: Dict[int, Set[str]] = {}
        # set of stopwords
        self._stopwords: Set[str] = set()
        # (guild_id, channel_id, topic_id) -> TopicMentionStats
        self._topic_mentions: Dict[tuple[int, int, int], TopicMentionStats] = defaultdict(
            TopicMentionStats
        )
        # (guild_id, channel_id, word) -> UnknownWordStats
        self._unknown_words: Dict[tuple[int, int, str], UnknownWordStats] = defaultdict(
            UnknownWordStats
        )
        # (guild_id, channel_id, word) -> WordFrequencyStats
        # Tracks ALL words (including stopwords) for phrase correlation detection
        self._word_frequency: Dict[tuple[int, int, str], WordFrequencyStats] = defaultdict(
            WordFrequencyStats
        )
        # Track the current date for daily topic submission
        self._current_date: date = datetime.now(timezone.utc).date()
        # Flag for whether aliases have been loaded
        self._aliases_loaded: bool = False
        # Flag to indicate shutdown/pickle save in progress
        self._saving_state: bool = False

    def _get_hour_bucket(self) -> datetime:
        """Get the current hour bucket (truncated to hour)."""
        now = datetime.now(timezone.utc)
        return now.replace(minute=0, second=0, microsecond=0)

    def _maybe_rotate_hour(self) -> bool:
        """Check if we've moved to a new hour and need to rotate."""
        current = self._get_hour_bucket()
        if current > self._current_hour:
            self._current_hour = current
            return True
        return False

    @listen(Startup)
    async def on_startup(self):
        """Start the aggregation tasks and load topic aliases."""
        self.hourly_aggregation.start()
        self.topic_aggregation.start()
        await self._load_topic_aliases()
        self._load_persisted_state()
        logger.info("Analytics collector started")

    async def _load_topic_aliases(self) -> None:
        """Load topic aliases, context words, and stopwords from the API for caching."""
        try:
            api = get_api_client()

            # Load topic aliases
            aliases = await api.get_topic_aliases()

            # Load category context words
            context_data = await api.get_context_words()

            # Load stopwords
            stopwords_data = await api.get_stopwords()

            with self._lock:
                # Cache topic aliases
                self._topic_aliases.clear()
                for alias_data in aliases:
                    self._topic_aliases[alias_data["alias"].lower()] = CachedTopicAlias(
                        topic_id=alias_data["topic_id"],
                        category_id=alias_data["category_id"],
                        is_anchor=alias_data["is_anchor"],
                        is_ambiguous=alias_data["is_ambiguous"],
                        full_phrase=alias_data["full_phrase"].lower() if alias_data["full_phrase"] else None
                    )

                # Cache context words by category
                self._context_words.clear()
                for category in context_data:
                    category_id = category["category_id"]
                    self._context_words[category_id] = set(word.lower() for word in category["words"])

                # Cache stopwords
                self._stopwords = set(word["word"].lower() for word in stopwords_data)

                self._aliases_loaded = True

            logger.info(
                f"Loaded {len(self._topic_aliases)} topic aliases, "
                f"{sum(len(words) for words in self._context_words.values())} context words, "
                f"{len(self._stopwords)} stopwords"
            )
        except Exception as e:
            logger.error(f"Failed to load topic matching data: {e}")
            # Don't block startup, but mark as not loaded
            self._aliases_loaded = False

    def _load_persisted_state(self) -> None:
        """Load persisted analytics state from previous shutdown."""
        if not ANALYTICS_PICKLE_PATH.exists():
            logger.info("No persisted analytics state found")
            return

        try:
            with open(ANALYTICS_PICKLE_PATH, "rb") as f:
                state = pickle.load(f)

            with self._lock:
                # Restore topic mentions
                if "topic_mentions" in state:
                    for key, data in state["topic_mentions"].items():
                        stats = TopicMentionStats(
                            mention_count=data["mention_count"],
                            user_ids=set(data["user_ids"]),
                        )
                        self._topic_mentions[key] = stats

                # Restore unknown words
                if "unknown_words" in state:
                    for key, data in state["unknown_words"].items():
                        stats = UnknownWordStats(
                            mention_count=data["mention_count"],
                            user_ids=set(data["user_ids"]),
                        )
                        self._unknown_words[key] = stats

                # Restore word frequency
                if "word_frequency" in state:
                    for key, data in state["word_frequency"].items():
                        stats = WordFrequencyStats(
                            mention_count=data["mention_count"],
                        )
                        self._word_frequency[key] = stats

                # Restore date
                if "current_date" in state:
                    self._current_date = state["current_date"]

            topic_count = len(state.get("topic_mentions", {}))
            word_count = len(state.get("unknown_words", {}))
            freq_count = len(state.get("word_frequency", {}))
            logger.info(
                f"Restored persisted state: {topic_count} topic entries, "
                f"{word_count} unknown word entries, {freq_count} word frequencies"
            )

            # Remove pickle file after loading
            ANALYTICS_PICKLE_PATH.unlink()

        except Exception as e:
            logger.error(f"Failed to load persisted analytics state: {e}")
            # Delete corrupted pickle file
            if ANALYTICS_PICKLE_PATH.exists():
                ANALYTICS_PICKLE_PATH.unlink()

    def save_state(self) -> None:
        """Save current analytics state to pickle file for persistence across restarts."""
        self._saving_state = True
        with self._lock:
            # Skip if no data to save
            if not self._topic_mentions and not self._unknown_words and not self._word_frequency:
                logger.debug("No analytics state to persist")
                return

            # Convert to serializable format
            state = {
                "current_date": self._current_date,
                "topic_mentions": {
                    key: {
                        "mention_count": stats.mention_count,
                        "user_ids": list(stats.user_ids),
                    }
                    for key, stats in self._topic_mentions.items()
                },
                "unknown_words": {
                    key: {
                        "mention_count": stats.mention_count,
                        "user_ids": list(stats.user_ids),
                    }
                    for key, stats in self._unknown_words.items()
                },
                "word_frequency": {
                    key: {
                        "mention_count": stats.mention_count,
                    }
                    for key, stats in self._word_frequency.items()
                },
            }

        try:
            ANALYTICS_PICKLE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(ANALYTICS_PICKLE_PATH, "wb") as f:
                pickle.dump(state, f)

            logger.info(
                f"Saved analytics state: {len(state['topic_mentions'])} topic entries, "
                f"{len(state['unknown_words'])} unknown word entries, "
                f"{len(state['word_frequency'])} word frequencies"
            )
        except Exception as e:
            logger.error(f"Failed to save analytics state: {e}")

    @listen(MessageCreate)
    async def on_message(self, event: MessageCreate):
        """Track message creation and topic mentions."""
        message = event.message

        # Ignore DMs and bot messages
        if not message.guild or message.author.bot:
            return

        guild_id = int(message.guild.id)
        channel_id = int(message.channel.id)
        user_id = int(message.author.id)

        with self._lock:
            # Guild-level stats
            guild_stats = self._guild_stats[guild_id]
            guild_stats.messages += 1
            guild_stats.active_users.add(user_id)

            # Channel-level stats
            channel_key = (guild_id, channel_id)
            channel_stats = self._channel_stats[channel_key]
            channel_stats.messages += 1
            channel_stats.active_users.add(user_id)

            # Topic tracking (only if aliases are loaded)
            if self._aliases_loaded and message.content:
                self._process_message_for_topics(
                    message.content, guild_id, channel_id, user_id
                )

    def _is_context_word_nearby(
        self, words: List[str], index: int, category_id: int, max_distance: int = 3
    ) -> bool:
        """Check if a context word for the category appears within max_distance of the index.

        Must be called while holding self._lock.
        """
        context_words = self._context_words.get(category_id, set())
        if not context_words:
            return False

        # Check words before
        start = max(0, index - max_distance)
        for i in range(start, index):
            if words[i] in context_words:
                return True

        # Check words after
        end = min(len(words), index + max_distance + 1)
        for i in range(index + 1, end):
            if words[i] in context_words:
                return True

        return False

    def _process_message_for_topics(
        self, content: str, guild_id: int, channel_id: int, user_id: int
    ) -> None:
        """Extract words from message and track topic mentions with tier-based matching.

        Tier 1 - Direct Match: Non-anchor, non-ambiguous aliases always count
        Tier 2 - Full Phrase Match: Anchor/ambiguous word + full phrase in message
        Tier 3 - Context Match: Anchor/ambiguous word + nearby context word
        Tier 4 - Unsupported: Anchor/ambiguous word without support (don't count)

        Also tracks ALL word frequencies for phrase correlation detection.

        Must be called while holding self._lock.
        """
        content_lower = content.lower()
        words = WORD_PATTERN.findall(content_lower)
        seen_topics: Set[int] = set()  # Track topics already counted for this message
        seen_words: Set[str] = set()   # Track unknown words already counted
        seen_freq_words: Set[str] = set()  # Track words for frequency (avoid duplicates)

        for idx, word in enumerate(words):
            # Track word frequency for ALL words (including stopwords)
            # This enables phrase correlation detection
            if (
                len(word) >= MIN_WORD_LENGTH
                and len(word) <= MAX_WORD_LENGTH
                and word not in seen_freq_words
            ):
                seen_freq_words.add(word)
                freq_key = (guild_id, channel_id, word)
                self._word_frequency[freq_key].mention_count += 1

            # Check if word matches a topic alias
            cached_alias = self._topic_aliases.get(word)

            if cached_alias is not None:
                # TIER 1: Direct match (non-anchor, non-ambiguous)
                if not cached_alias.is_anchor and not cached_alias.is_ambiguous:
                    if cached_alias.topic_id not in seen_topics:
                        seen_topics.add(cached_alias.topic_id)
                        key = (guild_id, channel_id, cached_alias.topic_id)
                        self._topic_mentions[key].mention_count += 1
                        self._topic_mentions[key].user_ids.add(user_id)
                else:
                    # Anchor or ambiguous word - needs context support
                    should_count = False

                    # TIER 2: Full phrase in message?
                    if cached_alias.full_phrase and cached_alias.full_phrase in content_lower:
                        should_count = True

                    # TIER 3: Context word nearby?
                    elif self._is_context_word_nearby(words, idx, cached_alias.category_id):
                        should_count = True

                    # TIER 4: No support → don't count (implicit)

                    if should_count and cached_alias.topic_id not in seen_topics:
                        seen_topics.add(cached_alias.topic_id)
                        key = (guild_id, channel_id, cached_alias.topic_id)
                        self._topic_mentions[key].mention_count += 1
                        self._topic_mentions[key].user_ids.add(user_id)

            # Unknown words (not a known alias)
            elif (
                len(word) >= MIN_WORD_LENGTH
                and len(word) <= MAX_WORD_LENGTH  # Avoid very long strings like URLs
                and word not in self._stopwords
                and word not in seen_words
            ):
                seen_words.add(word)
                key = (guild_id, channel_id, word)
                self._unknown_words[key].mention_count += 1
                self._unknown_words[key].user_ids.add(user_id)

    @listen(VoiceStateUpdate)
    async def on_voice_state_update(self, event: VoiceStateUpdate):
        """Track voice session starts and ends."""
        before = event.before
        after = event.after

        # Determine if user joined, left, or moved channels
        before_channel = before.channel if before else None
        after_channel = after.channel if after else None

        # Get guild from the state that has it
        state = after or before
        if not state or not state.guild:
            return

        guild_id = int(state.guild.id)
        user_id = int(state.user_id)

        # Ignore bots
        member = state.member
        if member and member.bot:
            return

        now = datetime.now(timezone.utc)
        session_key = (guild_id, user_id)

        with self._lock:
            # User left a voice channel
            if before_channel and (not after_channel or after_channel.id != before_channel.id):
                if session_key in self._voice_sessions:
                    session = self._voice_sessions.pop(session_key)
                    # Calculate minutes spent
                    duration = (now - session.started_at).total_seconds()
                    minutes = int(duration / 60)
                    if minutes > 0:
                        self._guild_stats[guild_id].voice_minutes += minutes
                        self._guild_stats[guild_id].active_users.add(user_id)

            # User joined a voice channel
            if after_channel and (not before_channel or before_channel.id != after_channel.id):
                self._voice_sessions[session_key] = VoiceSession(
                    guild_id=guild_id,
                    channel_id=int(after_channel.id),
                    user_id=user_id,
                    started_at=now,
                )

    @listen(MemberAdd)
    async def on_member_join(self, event: MemberAdd):
        """Track member joins."""
        member = event.member
        if not member.guild or member.bot:
            return

        guild_id = int(member.guild.id)

        with self._lock:
            self._guild_stats[guild_id].members_joined += 1

    @listen(MemberRemove)
    async def on_member_remove(self, event: MemberRemove):
        """Track member leaves."""
        member = event.member
        if not member.guild or member.bot:
            return

        guild_id = int(member.guild.id)

        with self._lock:
            self._guild_stats[guild_id].members_left += 1

    def _collect_and_reset(self) -> tuple[datetime, dict, dict]:
        """Collect current stats and reset counters. Returns (hour, guild_stats, channel_stats)."""
        with self._lock:
            hour = self._current_hour

            # Calculate voice minutes for still-active sessions
            now = datetime.now(timezone.utc)
            for session_key, session in self._voice_sessions.items():
                duration = (now - session.started_at).total_seconds()
                minutes = int(duration / 60)
                if minutes > 0:
                    self._guild_stats[session.guild_id].voice_minutes += minutes
                    self._guild_stats[session.guild_id].active_users.add(session.user_id)
                # Reset session start time for next hour
                self._voice_sessions[session_key] = VoiceSession(
                    guild_id=session.guild_id,
                    channel_id=session.channel_id,
                    user_id=session.user_id,
                    started_at=now,
                )

            # Collect guild stats
            guild_data = {}
            for guild_id, stats in self._guild_stats.items():
                guild_data[guild_id] = {
                    "messages": stats.messages,
                    "voice_minutes": stats.voice_minutes,
                    "active_users": len(stats.active_users),
                    "members_joined": stats.members_joined,
                    "members_left": stats.members_left,
                }

            # Collect channel stats
            channel_data = {}
            for (guild_id, channel_id), stats in self._channel_stats.items():
                if guild_id not in channel_data:
                    channel_data[guild_id] = {}
                channel_data[guild_id][channel_id] = {
                    "messages": stats.messages,
                    "active_users": len(stats.active_users),
                }

            # Reset counters
            self._guild_stats.clear()
            self._channel_stats.clear()
            self._current_hour = self._get_hour_bucket()

            return hour, guild_data, channel_data

    def _collect_and_reset_topics(self) -> tuple[date, dict, dict]:
        """Collect topic stats and reset counters.

        Returns (date, topic_mentions, unknown_words).
        Word frequency is collected separately via _collect_and_reset_word_frequency().
        """
        with self._lock:
            current_date = self._current_date

            # Collect topic mentions
            # Structure: guild_id -> channel_id -> list of mention data
            topic_data: Dict[int, Dict[int, list]] = {}
            for (guild_id, channel_id, topic_id), stats in self._topic_mentions.items():
                if guild_id not in topic_data:
                    topic_data[guild_id] = {}
                if channel_id not in topic_data[guild_id]:
                    topic_data[guild_id][channel_id] = []
                topic_data[guild_id][channel_id].append({
                    "topic_id": topic_id,
                    "mention_count": stats.mention_count,
                    "user_ids": list(stats.user_ids),
                })

            # Collect unknown words
            # Structure: guild_id -> channel_id -> list of word data
            word_data: Dict[int, Dict[int, list]] = {}
            for (guild_id, channel_id, word), stats in self._unknown_words.items():
                if guild_id not in word_data:
                    word_data[guild_id] = {}
                if channel_id not in word_data[guild_id]:
                    word_data[guild_id][channel_id] = []
                word_data[guild_id][channel_id].append({
                    "word": word,
                    "mention_count": stats.mention_count,
                    "user_ids": list(stats.user_ids),
                })

            # Reset topic counters (but NOT word_frequency - that's hourly)
            self._topic_mentions.clear()
            self._unknown_words.clear()
            self._current_date = datetime.now(timezone.utc).date()

            return current_date, topic_data, word_data

    def _collect_and_reset_word_frequency(self) -> tuple[date, dict]:
        """Collect word frequency stats and reset counters.

        Returns (date, word_frequency).
        Word frequency is filtered to only include words with 10+ mentions per guild.
        Called hourly to batch database writes.
        """
        with self._lock:
            current_date = self._current_date

            # Aggregate by guild/word to check threshold
            guild_word_totals: Dict[tuple[int, str], int] = defaultdict(int)
            for (guild_id, channel_id, word), stats in self._word_frequency.items():
                guild_word_totals[(guild_id, word)] += stats.mention_count

            # Collect only words that meet the threshold
            # Structure: guild_id -> channel_id -> list of frequency data
            freq_data: Dict[int, Dict[int, list]] = {}
            for (guild_id, channel_id, word), stats in self._word_frequency.items():
                if guild_word_totals[(guild_id, word)] >= FREQ_MIN_MENTIONS:
                    if guild_id not in freq_data:
                        freq_data[guild_id] = {}
                    if channel_id not in freq_data[guild_id]:
                        freq_data[guild_id][channel_id] = []
                    freq_data[guild_id][channel_id].append({
                        "word": word,
                        "mention_count": stats.mention_count,
                    })

            # Reset word frequency counters
            self._word_frequency.clear()

            return current_date, freq_data

    async def _get_member_counts(self) -> Dict[int, int]:
        """Get current member counts for all guilds."""
        counts = {}
        for guild in self.bot.guilds:
            counts[int(guild.id)] = guild.member_count or 0
        return counts

    @Task.create(IntervalTrigger(minutes=60))
    async def hourly_aggregation(self):
        """Submit hourly analytics and word frequency data to the API."""
        if not self.bot.is_ready:
            return

        try:
            hour, guild_stats, channel_stats = self._collect_and_reset()

            # Skip if no data
            if not guild_stats and not channel_stats:
                logger.debug("No analytics data to submit for this hour")
            else:
                # Get current member counts
                member_counts = await self._get_member_counts()

                # Add member counts to guild stats
                for guild_id, count in member_counts.items():
                    if guild_id not in guild_stats:
                        guild_stats[guild_id] = {
                            "messages": 0,
                            "voice_minutes": 0,
                            "active_users": 0,
                            "members_joined": 0,
                            "members_left": 0,
                        }
                    guild_stats[guild_id]["member_count"] = count

                # Submit to API
                api = get_api_client()
                await api.submit_hourly_analytics(
                    timestamp=hour,
                    guild_stats=guild_stats,
                    channel_stats=channel_stats,
                )

                logger.info(
                    f"Submitted hourly analytics: {len(guild_stats)} guilds, "
                    f"{sum(len(ch) for ch in channel_stats.values())} channels"
                )

        except Exception as e:
            logger.error(f"Failed to submit hourly analytics: {e}")

        # Submit word frequency data (batched hourly for efficiency)
        await self._submit_word_frequency()

    @Task.create(IntervalTrigger(minutes=5))
    async def topic_aggregation(self):
        """Submit topic data to the API every 5 minutes."""
        if not self.bot.is_ready:
            return

        # Skip if shutdown/pickle save is in progress
        if self._saving_state:
            logger.info("Topic aggregation skipped - state save in progress")
            return

        await self._submit_topic_data()

    async def _submit_topic_data(self) -> None:
        """Collect and submit topic tracking data (every 5 minutes)."""
        try:
            topic_date, topic_mentions, unknown_words = self._collect_and_reset_topics()

            # Skip if no topic data
            if not topic_mentions and not unknown_words:
                logger.debug("No topic data to submit")
                return

            api = get_api_client()
            await api.submit_topic_data(
                date=datetime.combine(topic_date, datetime.min.time()),
                topic_mentions=topic_mentions,
                unknown_words=unknown_words,
            )

            mention_count = sum(
                len(channels)
                for channels in topic_mentions.values()
            )
            word_count = sum(len(words) for words in unknown_words.values())

            logger.info(
                f"Submitted topic data: {mention_count} topic entries, "
                f"{word_count} unknown word entries for {topic_date.isoformat()}"
            )

        except Exception as e:
            logger.error(f"Failed to submit topic data: {e}")

    async def _submit_word_frequency(self) -> None:
        """Collect and submit word frequency data (hourly batch)."""
        try:
            freq_date, word_frequency = self._collect_and_reset_word_frequency()

            # Skip if no frequency data
            if not word_frequency:
                logger.debug("No word frequency data to submit")
                return

            api = get_api_client()
            await api.submit_word_frequency(
                date=datetime.combine(freq_date, datetime.min.time()),
                word_frequency=word_frequency,
            )

            freq_count = sum(
                sum(len(words) for words in channels.values())
                for channels in word_frequency.values()
            )

            logger.info(
                f"Submitted word frequency batch: {freq_count} entries "
                f"for {freq_date.isoformat()}"
            )

        except Exception as e:
            logger.error(f"Failed to submit word frequency: {e}")


def setup(bot):
    AnalyticsCollector(bot)
