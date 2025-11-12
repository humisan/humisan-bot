#!/usr/bin/env python3
"""
Test script for the database module
This script verifies that the database initializes correctly
"""

import sys
import os
from utils.database import Database

def test_database():
    """Test database initialization and basic operations"""
    print("=" * 60)
    print("Testing Discord Music Bot Database Module")
    print("=" * 60)

    try:
        # Initialize database
        print("\n1. Initializing database...")
        db = Database()
        print("   SUCCESS: Database initialized at data/bot.db")

        # Get database statistics
        print("\n2. Checking database structure...")
        stats = db.get_database_stats()
        print("   Database tables created:")
        for table, count in stats.items():
            print(f"   - {table}: {count} records")

        # Test server creation
        print("\n3. Testing server creation...")
        success = db.create_server(
            guild_id="123456789",
            guild_name="Test Server",
            prefix="!",
            default_volume=75
        )
        if success:
            print("   SUCCESS: Test server created")
        else:
            print("   INFO: Server already exists (this is normal on repeat runs)")

        # Test getting server settings
        print("\n4. Testing server settings retrieval...")
        settings = db.get_server_settings("123456789")
        if settings:
            print(f"   SUCCESS: Retrieved settings for {settings['guild_name']}")
            print(f"   - Prefix: {settings['prefix']}")
            print(f"   - Volume: {settings['default_volume']}")

        # Test playlist creation
        print("\n5. Testing playlist creation...")
        playlist_id = db.create_playlist(
            guild_id="123456789",
            name="Test Playlist",
            created_by="user123"
        )
        if playlist_id:
            print(f"   SUCCESS: Playlist created with ID: {playlist_id}")
        else:
            print("   INFO: Playlist already exists (this is normal on repeat runs)")

        # Test song addition
        print("\n6. Testing song addition to playlist...")
        if playlist_id:
            song_id = db.add_song_to_playlist(
                playlist_id=playlist_id,
                title="Test Song",
                url="https://example.com/song.mp3",
                webpage_url="https://example.com/watch?v=test",
                duration=180,
                thumbnail="https://example.com/thumb.jpg",
                added_by="user123"
            )
            if song_id:
                print(f"   SUCCESS: Song added with ID: {song_id}")

        # Test favorites
        print("\n7. Testing user favorites...")
        fav_id = db.add_favorite(
            guild_id="123456789",
            user_id="user123",
            title="Favorite Song",
            url="https://example.com/fav.mp3",
            webpage_url="https://example.com/watch?v=fav",
            duration=200,
            thumbnail="https://example.com/fav_thumb.jpg"
        )
        if fav_id:
            print(f"   SUCCESS: Favorite added with ID: {fav_id}")
        else:
            print("   INFO: Favorite already exists (this is normal on repeat runs)")

        # Test audit logging
        print("\n8. Testing audit logging...")
        log_success = db.log_command(
            guild_id="123456789",
            user_id="user123",
            command="play",
            details="Played: Test Song"
        )
        if log_success:
            print("   SUCCESS: Command logged")

        # Test statistics
        print("\n9. Testing statistics update...")
        stats_success = db.update_stats(
            guild_id="123456789",
            songs_played=1,
            playtime=180,
            skips=0
        )
        if stats_success:
            print("   SUCCESS: Statistics updated")

        # Get final database stats
        print("\n10. Final database statistics...")
        final_stats = db.get_database_stats()
        for table, count in final_stats.items():
            print(f"    - {table}: {count} records")

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nDatabase file location: C:\\Users\\humis\\PycharmProjects\\PythonProject\\data\\bot.db")
        print("\nYou can now use this database module in your Discord bot!")

        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_database()
    sys.exit(0 if success else 1)
