# Database Module Usage Guide

## Overview

The comprehensive SQLite database module for the Discord music bot is located at:
```
C:\Users\humis\PycharmProjects\PythonProject\utils\database.py
```

Database file location:
```
C:\Users\humis\PycharmProjects\PythonProject\data\bot.db
```

## Database Schema

### Tables

1. **servers** - Guild-specific settings
   - `guild_id` (TEXT, PRIMARY KEY)
   - `guild_name` (TEXT)
   - `prefix` (TEXT, default: '!')
   - `notification_channel_id` (TEXT)
   - `default_volume` (INTEGER, default: 50)
   - `created_at` (DATETIME)
   - `updated_at` (DATETIME)

2. **playlists** - Custom playlists per guild
   - `id` (INTEGER, PRIMARY KEY)
   - `guild_id` (TEXT, FOREIGN KEY)
   - `name` (TEXT)
   - `created_by` (TEXT)
   - `created_at` (DATETIME)

3. **songs** - Songs in playlists
   - `id` (INTEGER, PRIMARY KEY)
   - `playlist_id` (INTEGER, FOREIGN KEY)
   - `title` (TEXT)
   - `url` (TEXT)
   - `webpage_url` (TEXT)
   - `duration` (INTEGER)
   - `thumbnail` (TEXT)
   - `added_by` (TEXT)
   - `added_at` (DATETIME)

4. **user_favorites** - User favorite songs
   - `id` (INTEGER, PRIMARY KEY)
   - `guild_id` (TEXT, FOREIGN KEY)
   - `user_id` (TEXT)
   - `title` (TEXT)
   - `url` (TEXT)
   - `webpage_url` (TEXT)
   - `duration` (INTEGER)
   - `thumbnail` (TEXT)
   - `added_at` (DATETIME)

5. **audit_logs** - Command execution logs
   - `id` (INTEGER, PRIMARY KEY)
   - `guild_id` (TEXT, FOREIGN KEY)
   - `user_id` (TEXT)
   - `command` (TEXT)
   - `details` (TEXT)
   - `executed_at` (DATETIME)

6. **bot_stats** - Daily usage statistics
   - `id` (INTEGER, PRIMARY KEY)
   - `guild_id` (TEXT, FOREIGN KEY)
   - `songs_played` (INTEGER)
   - `total_playtime` (INTEGER)
   - `total_skips` (INTEGER)
   - `date` (DATE)

## Usage Examples

### Initialize Database

```python
from utils.database import Database

# Initialize with default path (data/bot.db)
db = Database()

# Or specify custom path
db = Database(db_path='custom/path/bot.db')
```

### Server Settings

```python
# Create server entry
db.create_server(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name,
    prefix='!',
    notification_channel_id=str(channel.id),
    default_volume=50
)

# Get server settings
settings = db.get_server_settings(str(ctx.guild.id))
if settings:
    print(f"Prefix: {settings['prefix']}")
    print(f"Volume: {settings['default_volume']}")

# Update server settings
db.update_server_settings(
    guild_id=str(ctx.guild.id),
    prefix='?',
    default_volume=75
)
```

### Playlists

```python
# Create playlist
playlist_id = db.create_playlist(
    guild_id=str(ctx.guild.id),
    name="My Playlist",
    created_by=str(ctx.author.id)
)

# Get playlist by ID
playlist = db.get_playlist(playlist_id)

# Get playlist by name
playlist = db.get_playlist_by_name(
    guild_id=str(ctx.guild.id),
    name="My Playlist"
)

# Get all playlists for a guild
playlists = db.get_all_playlists(str(ctx.guild.id))
for playlist in playlists:
    print(f"Playlist: {playlist['name']}")

# Delete playlist
db.delete_playlist(playlist_id)
```

### Songs

```python
# Add song to playlist
song_id = db.add_song_to_playlist(
    playlist_id=playlist_id,
    title="Song Title",
    url="https://example.com/audio.mp3",
    webpage_url="https://youtube.com/watch?v=xxxxx",
    duration=180,  # seconds
    thumbnail="https://i.ytimg.com/vi/xxxxx/default.jpg",
    added_by=str(ctx.author.id)
)

# Get all songs from playlist
songs = db.get_songs_from_playlist(playlist_id)
for song in songs:
    print(f"{song['title']} - {song['duration']}s")

# Remove song from playlist
db.remove_song_from_playlist(song_id)
```

### User Favorites

```python
# Add favorite
fav_id = db.add_favorite(
    guild_id=str(ctx.guild.id),
    user_id=str(ctx.author.id),
    title="Favorite Song",
    url="https://example.com/song.mp3",
    webpage_url="https://youtube.com/watch?v=xxxxx",
    duration=240,
    thumbnail="https://i.ytimg.com/vi/xxxxx/default.jpg"
)

# Get user favorites
favorites = db.get_user_favorites(
    guild_id=str(ctx.guild.id),
    user_id=str(ctx.author.id)
)
for fav in favorites:
    print(f"Favorite: {fav['title']}")

# Delete favorite by ID
db.delete_favorite(fav_id)

# Delete favorite by URL
db.delete_favorite_by_url(
    guild_id=str(ctx.guild.id),
    user_id=str(ctx.author.id),
    url="https://example.com/song.mp3"
)
```

### Audit Logs

```python
# Log command execution
db.log_command(
    guild_id=str(ctx.guild.id),
    user_id=str(ctx.author.id),
    command="play",
    details=f"Played: {song_title}"
)

# Get audit logs (all)
logs = db.get_audit_logs(
    guild_id=str(ctx.guild.id),
    limit=100
)

# Get audit logs (filtered by user)
user_logs = db.get_audit_logs(
    guild_id=str(ctx.guild.id),
    user_id=str(ctx.author.id),
    limit=50
)

# Get audit logs (filtered by command)
command_logs = db.get_audit_logs(
    guild_id=str(ctx.guild.id),
    command="play",
    limit=50
)

# Clear old logs (older than 30 days)
deleted_count = db.clear_old_audit_logs(days=30)
print(f"Deleted {deleted_count} old logs")
```

### Statistics

```python
# Update statistics (called when songs are played)
db.update_stats(
    guild_id=str(ctx.guild.id),
    songs_played=1,
    playtime=180,  # seconds
    skips=0
)

# Get statistics for last 7 days
stats = db.get_stats(
    guild_id=str(ctx.guild.id),
    days=7
)
for day_stats in stats:
    print(f"{day_stats['date']}: {day_stats['songs_played']} songs")

# Get total accumulated statistics
total_stats = db.get_total_stats(str(ctx.guild.id))
if total_stats:
    print(f"Total songs: {total_stats['total_songs']}")
    print(f"Total playtime: {total_stats['total_playtime']}s")
    print(f"Total skips: {total_stats['total_skips']}")
    print(f"Days active: {total_stats['days_active']}")
```

### Utility Methods

```python
# Clean up orphaned data
db.cleanup_orphaned_data()

# Get database statistics (record counts)
stats = db.get_database_stats()
for table, count in stats.items():
    print(f"{table}: {count} records")

# Optimize database
db.vacuum_database()
```

## Integration with Discord Bot

### Example: Music Cog Integration

```python
import discord
from discord.ext import commands
from utils.database import Database

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.command()
    async def play(self, ctx, *, query):
        """Play a song"""
        # Your music playing logic here

        # Log the command
        self.db.log_command(
            guild_id=str(ctx.guild.id),
            user_id=str(ctx.author.id),
            command="play",
            details=f"Query: {query}"
        )

        # Update statistics
        self.db.update_stats(
            guild_id=str(ctx.guild.id),
            songs_played=1,
            playtime=duration  # from song info
        )

    @commands.command()
    async def playlist_create(self, ctx, name: str):
        """Create a new playlist"""
        playlist_id = self.db.create_playlist(
            guild_id=str(ctx.guild.id),
            name=name,
            created_by=str(ctx.author.id)
        )

        if playlist_id:
            await ctx.send(f"Created playlist: {name}")
        else:
            await ctx.send(f"Playlist '{name}' already exists!")

    @commands.command()
    async def favorite(self, ctx):
        """Add current song to favorites"""
        # Get current song info
        song_info = self.get_current_song()

        fav_id = self.db.add_favorite(
            guild_id=str(ctx.guild.id),
            user_id=str(ctx.author.id),
            title=song_info['title'],
            url=song_info['url'],
            webpage_url=song_info['webpage_url'],
            duration=song_info['duration'],
            thumbnail=song_info['thumbnail']
        )

        if fav_id:
            await ctx.send("Added to your favorites!")
        else:
            await ctx.send("This song is already in your favorites!")

    @commands.command()
    async def stats(self, ctx):
        """Show bot statistics"""
        total_stats = self.db.get_total_stats(str(ctx.guild.id))

        if total_stats:
            embed = discord.Embed(title="Bot Statistics", color=discord.Color.blue())
            embed.add_field(name="Total Songs Played", value=total_stats['total_songs'])
            embed.add_field(name="Total Playtime", value=f"{total_stats['total_playtime']} seconds")
            embed.add_field(name="Days Active", value=total_stats['days_active'])
            await ctx.send(embed=embed)
```

## Error Handling

All database methods include comprehensive error handling and logging:

```python
try:
    playlist_id = db.create_playlist(
        guild_id=str(ctx.guild.id),
        name="My Playlist",
        created_by=str(ctx.author.id)
    )
    if playlist_id:
        print(f"Success: Playlist ID {playlist_id}")
    else:
        print("Failed: Playlist already exists or error occurred")
except Exception as e:
    print(f"Error: {e}")
```

## Features

- **Automatic table creation** on first run
- **Foreign key constraints** for data integrity
- **Cascade deletion** when guilds leave
- **Unique constraints** to prevent duplicates
- **Indexes** for optimized queries
- **Connection pooling** with proper cleanup
- **Row factory** for dictionary-style access
- **Comprehensive logging** via utils.logger
- **Transaction support** with rollback on errors

## Testing

Run the test script to verify everything works:

```bash
python test_database.py
```

## Maintenance

### Regular Maintenance Tasks

```python
# Clean old audit logs (monthly)
db.clear_old_audit_logs(days=30)

# Clean orphaned data
db.cleanup_orphaned_data()

# Optimize database (weekly)
db.vacuum_database()
```

## Notes

- All guild_id and user_id values should be strings
- Duration is stored in seconds (integer)
- Foreign keys are enabled automatically
- Database connections are properly closed after each operation
- All timestamps use SQLite's CURRENT_TIMESTAMP
- The database file is created automatically in the data/ directory

## Support

For issues or questions about the database module:
1. Check the logger output in bot.log
2. Review the comprehensive error messages
3. Verify your database path and permissions
4. Run the test script to diagnose issues
