#!/usr/bin/env python3
"""Test script for channel-level quickembed settings."""

import os
import sys
import asyncio
import tempfile

# Add bot directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.db import GuildDatabase


async def test_channel_quickembed():
    """Test channel-level quickembed functionality."""
    print("Starting channel-level quickembed tests...\n")

    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name

    try:
        db = GuildDatabase(db_path)
        await db.setup_db()
        print("✓ Database initialized successfully\n")

        guild_id = 123456789
        channel_id_1 = 111111111
        channel_id_2 = 222222222

        # Test 1: Default settings (no configuration)
        print("Test 1: Default settings")
        platforms, is_default = db.get_quickembed_platforms(guild_id)
        assert is_default == True, "Should use default settings"
        assert 'insta' in platforms, "Default should include insta"
        print(f"✓ Default platforms: {', '.join(platforms)}\n")

        # Test 2: Set guild-level setting
        print("Test 2: Set guild-level setting")
        success, error, valid = db.set_quickembed_platforms(guild_id, "twitch,kick")
        assert success == True, f"Should succeed: {error}"
        platforms, is_default = db.get_quickembed_platforms(guild_id)
        assert is_default == False, "Should not be default"
        assert set(platforms) == {'twitch', 'kick'}, f"Should have twitch,kick but got {platforms}"
        print(f"✓ Guild-level set to: {', '.join(platforms)}\n")

        # Test 3: Set channel-specific override
        print("Test 3: Set channel-specific override")
        success, error, valid = db.set_quickembed_platforms(guild_id, "all", channel_id_1)
        assert success == True, f"Should succeed: {error}"
        platforms, is_default = db.get_quickembed_platforms(guild_id, channel_id_1)
        assert is_default == False, "Should not be default"
        assert 'twitch' in platforms and 'insta' in platforms, "Should have all platforms"
        print(f"✓ Channel {channel_id_1} set to: all\n")

        # Test 4: Hierarchical fallback - channel with override
        print("Test 4: Hierarchical fallback - channel with override")
        platforms_ch1, _ = db.get_quickembed_platforms(guild_id, channel_id_1)
        platforms_guild, _ = db.get_quickembed_platforms(guild_id)
        assert len(platforms_ch1) > len(platforms_guild), "Channel should have more platforms (all vs guild)"
        print(f"✓ Channel override (all) takes precedence over guild setting (twitch,kick)\n")

        # Test 5: Hierarchical fallback - channel without override
        print("Test 5: Hierarchical fallback - channel without override")
        platforms_ch2, _ = db.get_quickembed_platforms(guild_id, channel_id_2)
        platforms_guild, _ = db.get_quickembed_platforms(guild_id)
        assert platforms_ch2 == platforms_guild, "Should use guild setting"
        print(f"✓ Channel without override uses guild setting: {', '.join(platforms_ch2)}\n")

        # Test 6: is_platform_quickembed_enabled
        print("Test 6: is_platform_quickembed_enabled")
        assert db.is_platform_quickembed_enabled(guild_id, "Twitch") == True, "Twitch should be enabled at guild level"
        assert db.is_platform_quickembed_enabled(guild_id, "Instagram") == False, "Instagram should be disabled at guild level"
        assert db.is_platform_quickembed_enabled(guild_id, "Instagram", channel_id_1) == True, "Instagram should be enabled in channel 1 (all)"
        assert db.is_platform_quickembed_enabled(guild_id, "Instagram", channel_id_2) == False, "Instagram should be disabled in channel 2 (falls back to guild)"
        print("✓ Platform checks working correctly\n")

        # Test 7: Set channel to 'none'
        print("Test 7: Set channel to 'none'")
        success, error, valid = db.set_quickembed_platforms(guild_id, "none", channel_id_2)
        assert success == True, f"Should succeed: {error}"
        platforms_ch2, _ = db.get_quickembed_platforms(guild_id, channel_id_2)
        assert platforms_ch2 == [], "Should have no platforms"
        print(f"✓ Channel {channel_id_2} disabled (none)\n")

        # Test 8: List channel overrides
        print("Test 8: List channel overrides")
        overrides = db.list_channel_overrides(guild_id)
        assert len(overrides) == 2, f"Should have 2 overrides but got {len(overrides)}"
        override_dict = {ch_id: setting for ch_id, setting in overrides}
        assert channel_id_1 in override_dict, "Should include channel 1"
        assert channel_id_2 in override_dict, "Should include channel 2"
        print(f"✓ Found {len(overrides)} channel overrides\n")

        # Test 9: Delete channel override
        print("Test 9: Delete channel override")
        success = db.delete_channel_quickembed_setting(guild_id, channel_id_1)
        assert success == True, "Should succeed"
        platforms_ch1, _ = db.get_quickembed_platforms(guild_id, channel_id_1)
        platforms_guild, _ = db.get_quickembed_platforms(guild_id)
        assert platforms_ch1 == platforms_guild, "Should fall back to guild setting after deletion"
        overrides = db.list_channel_overrides(guild_id)
        assert len(overrides) == 1, f"Should have 1 override but got {len(overrides)}"
        print(f"✓ Channel override deleted, now using guild setting\n")

        # Test 10: Update existing channel override
        print("Test 10: Update existing channel override")
        success, error, valid = db.set_quickembed_platforms(guild_id, "insta,tiktok", channel_id_2)
        assert success == True, f"Should succeed: {error}"
        platforms_ch2, _ = db.get_quickembed_platforms(guild_id, channel_id_2)
        assert set(platforms_ch2) == {'insta', 'tiktok'}, f"Should have insta,tiktok but got {platforms_ch2}"
        print(f"✓ Channel override updated from 'none' to 'insta,tiktok'\n")

        print("=" * 50)
        print("ALL TESTS PASSED! ✓")
        print("=" * 50)

    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)
            print(f"\nCleaned up test database: {db_path}")


if __name__ == "__main__":
    asyncio.run(test_channel_quickembed())
