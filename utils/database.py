import sqlite3
import os
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Database:
    """Comprehensive database manager for Discord music bot"""

    def __init__(self, db_path: str = 'data/bot.db'):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file (default: data/bot.db)
        """
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self.init_database()
        logger.info(f"Database initialized at {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get database connection with foreign keys enabled

        Returns:
            SQLite connection object
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def init_database(self):
        """Initialize database with all required tables"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Servers table - Store guild-specific settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    guild_id TEXT PRIMARY KEY,
                    guild_name TEXT NOT NULL,
                    prefix TEXT DEFAULT '!',
                    notification_channel_id TEXT,
                    default_volume INTEGER DEFAULT 50,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Playlists table - Store custom playlists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id) REFERENCES servers(guild_id) ON DELETE CASCADE,
                    UNIQUE(guild_id, name)
                )
            ''')

            # Songs table - Store songs in playlists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS songs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    webpage_url TEXT,
                    duration INTEGER,
                    thumbnail TEXT,
                    added_by TEXT NOT NULL,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
                )
            ''')

            # User favorites table - Store individual user favorites
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    webpage_url TEXT,
                    duration INTEGER,
                    thumbnail TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id) REFERENCES servers(guild_id) ON DELETE CASCADE,
                    UNIQUE(guild_id, user_id, url)
                )
            ''')

            # Audit logs table - Track command usage
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    details TEXT,
                    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id) REFERENCES servers(guild_id) ON DELETE CASCADE
                )
            ''')

            # Bot statistics table - Track usage statistics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    songs_played INTEGER DEFAULT 0,
                    total_playtime INTEGER DEFAULT 0,
                    total_skips INTEGER DEFAULT 0,
                    date DATE DEFAULT (DATE('now')),
                    FOREIGN KEY (guild_id) REFERENCES servers(guild_id) ON DELETE CASCADE,
                    UNIQUE(guild_id, date)
                )
            ''')

            # Create indexes for better query performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_playlists_guild
                ON playlists(guild_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_songs_playlist
                ON songs(playlist_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_favorites_user
                ON user_favorites(guild_id, user_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_guild
                ON audit_logs(guild_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_stats_guild_date
                ON bot_stats(guild_id, date)
            ''')

            conn.commit()
            logger.info("All database tables initialized successfully")

        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==================== SERVER SETTINGS METHODS ====================

    def get_server_settings(self, guild_id: str) -> Optional[Dict[str, Any]]:
        """
        Get server settings

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary with server settings or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM servers WHERE guild_id = ?
            ''', (guild_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error getting server settings for {guild_id}: {e}")
            return None
        finally:
            conn.close()

    def create_server(self, guild_id: str, guild_name: str, prefix: str = '!',
                     notification_channel_id: Optional[str] = None,
                     default_volume: int = 50) -> bool:
        """
        Create new server entry

        Args:
            guild_id: Discord guild ID
            guild_name: Guild name
            prefix: Command prefix (default: '!')
            notification_channel_id: Channel for notifications
            default_volume: Default volume (0-100)

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO servers (guild_id, guild_name, prefix, notification_channel_id, default_volume)
                VALUES (?, ?, ?, ?, ?)
            ''', (guild_id, guild_name, prefix, notification_channel_id, default_volume))

            conn.commit()
            logger.info(f"Server {guild_name} ({guild_id}) created")
            return True

        except sqlite3.IntegrityError:
            logger.warning(f"Server {guild_id} already exists")
            return False
        except sqlite3.Error as e:
            logger.error(f"Error creating server {guild_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def update_server_settings(self, guild_id: str, **kwargs) -> bool:
        """
        Update server settings

        Args:
            guild_id: Discord guild ID
            **kwargs: Settings to update (prefix, notification_channel_id, default_volume, etc.)

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build dynamic UPDATE query
            valid_fields = ['guild_name', 'prefix', 'notification_channel_id', 'default_volume']
            updates = []
            values = []

            for key, value in kwargs.items():
                if key in valid_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)

            if not updates:
                logger.warning("No valid fields to update")
                return False

            # Add updated_at timestamp
            updates.append("updated_at = CURRENT_TIMESTAMP")
            values.append(guild_id)

            query = f"UPDATE servers SET {', '.join(updates)} WHERE guild_id = ?"
            cursor.execute(query, values)

            conn.commit()
            logger.info(f"Server settings updated for {guild_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error updating server settings for {guild_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ==================== PLAYLIST METHODS ====================

    def create_playlist(self, guild_id: str, name: str, created_by: str) -> Optional[int]:
        """
        Create new playlist

        Args:
            guild_id: Discord guild ID
            name: Playlist name
            created_by: User ID who created the playlist

        Returns:
            Playlist ID if successful, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO playlists (guild_id, name, created_by)
                VALUES (?, ?, ?)
            ''', (guild_id, name, created_by))

            playlist_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Playlist '{name}' created in guild {guild_id}")
            return playlist_id

        except sqlite3.IntegrityError:
            logger.warning(f"Playlist '{name}' already exists in guild {guild_id}")
            return None
        except sqlite3.Error as e:
            logger.error(f"Error creating playlist: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_playlist(self, playlist_id: int) -> Optional[Dict[str, Any]]:
        """
        Get playlist by ID

        Args:
            playlist_id: Playlist ID

        Returns:
            Dictionary with playlist info or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM playlists WHERE id = ?
            ''', (playlist_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error getting playlist {playlist_id}: {e}")
            return None
        finally:
            conn.close()

    def get_playlist_by_name(self, guild_id: str, name: str) -> Optional[Dict[str, Any]]:
        """
        Get playlist by name

        Args:
            guild_id: Discord guild ID
            name: Playlist name

        Returns:
            Dictionary with playlist info or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM playlists WHERE guild_id = ? AND name = ?
            ''', (guild_id, name))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error getting playlist '{name}' in guild {guild_id}: {e}")
            return None
        finally:
            conn.close()

    def get_all_playlists(self, guild_id: str) -> List[Dict[str, Any]]:
        """
        Get all playlists for a guild

        Args:
            guild_id: Discord guild ID

        Returns:
            List of playlist dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM playlists WHERE guild_id = ? ORDER BY created_at DESC
            ''', (guild_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting playlists for guild {guild_id}: {e}")
            return []
        finally:
            conn.close()

    def delete_playlist(self, playlist_id: int) -> bool:
        """
        Delete playlist and all its songs

        Args:
            playlist_id: Playlist ID

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM playlists WHERE id = ?
            ''', (playlist_id,))

            conn.commit()
            logger.info(f"Playlist {playlist_id} deleted")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error deleting playlist {playlist_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ==================== SONG METHODS ====================

    def add_song_to_playlist(self, playlist_id: int, title: str, url: str,
                            webpage_url: Optional[str], duration: Optional[int],
                            thumbnail: Optional[str], added_by: str) -> Optional[int]:
        """
        Add song to playlist

        Args:
            playlist_id: Playlist ID
            title: Song title
            url: Direct audio URL
            webpage_url: Original webpage URL
            duration: Song duration in seconds
            thumbnail: Thumbnail URL
            added_by: User ID who added the song

        Returns:
            Song ID if successful, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO songs (playlist_id, title, url, webpage_url, duration, thumbnail, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (playlist_id, title, url, webpage_url, duration, thumbnail, added_by))

            song_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Song '{title}' added to playlist {playlist_id}")
            return song_id

        except sqlite3.Error as e:
            logger.error(f"Error adding song to playlist {playlist_id}: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_songs_from_playlist(self, playlist_id: int) -> List[Dict[str, Any]]:
        """
        Get all songs from a playlist

        Args:
            playlist_id: Playlist ID

        Returns:
            List of song dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM songs WHERE playlist_id = ? ORDER BY added_at ASC
            ''', (playlist_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting songs from playlist {playlist_id}: {e}")
            return []
        finally:
            conn.close()

    def remove_song_from_playlist(self, song_id: int) -> bool:
        """
        Remove song from playlist

        Args:
            song_id: Song ID

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM songs WHERE id = ?
            ''', (song_id,))

            conn.commit()
            logger.info(f"Song {song_id} removed from playlist")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error removing song {song_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ==================== USER FAVORITES METHODS ====================

    def add_favorite(self, guild_id: str, user_id: str, title: str, url: str,
                    webpage_url: Optional[str], duration: Optional[int],
                    thumbnail: Optional[str]) -> Optional[int]:
        """
        Add song to user favorites

        Args:
            guild_id: Discord guild ID
            user_id: User ID
            title: Song title
            url: Direct audio URL
            webpage_url: Original webpage URL
            duration: Song duration in seconds
            thumbnail: Thumbnail URL

        Returns:
            Favorite ID if successful, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO user_favorites (guild_id, user_id, title, url, webpage_url, duration, thumbnail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (guild_id, user_id, title, url, webpage_url, duration, thumbnail))

            favorite_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Favorite '{title}' added for user {user_id} in guild {guild_id}")
            return favorite_id

        except sqlite3.IntegrityError:
            logger.warning(f"Song already in favorites for user {user_id}")
            return None
        except sqlite3.Error as e:
            logger.error(f"Error adding favorite: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_user_favorites(self, guild_id: str, user_id: str) -> List[Dict[str, Any]]:
        """
        Get user's favorite songs

        Args:
            guild_id: Discord guild ID
            user_id: User ID

        Returns:
            List of favorite song dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM user_favorites
                WHERE guild_id = ? AND user_id = ?
                ORDER BY added_at DESC
            ''', (guild_id, user_id))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting favorites for user {user_id}: {e}")
            return []
        finally:
            conn.close()

    def delete_favorite(self, favorite_id: int) -> bool:
        """
        Delete favorite song

        Args:
            favorite_id: Favorite ID

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM user_favorites WHERE id = ?
            ''', (favorite_id,))

            conn.commit()
            logger.info(f"Favorite {favorite_id} deleted")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error deleting favorite {favorite_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def delete_favorite_by_url(self, guild_id: str, user_id: str, url: str) -> bool:
        """
        Delete favorite by URL

        Args:
            guild_id: Discord guild ID
            user_id: User ID
            url: Song URL

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM user_favorites
                WHERE guild_id = ? AND user_id = ? AND url = ?
            ''', (guild_id, user_id, url))

            conn.commit()
            logger.info(f"Favorite deleted for user {user_id} (URL: {url})")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error deleting favorite by URL: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ==================== AUDIT LOG METHODS ====================

    def log_command(self, guild_id: str, user_id: str, command: str,
                   details: Optional[str] = None) -> bool:
        """
        Log command execution

        Args:
            guild_id: Discord guild ID
            user_id: User ID who executed the command
            command: Command name
            details: Additional details (optional)

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO audit_logs (guild_id, user_id, command, details)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, user_id, command, details))

            conn.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Error logging command: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_audit_logs(self, guild_id: str, limit: int = 100,
                      user_id: Optional[str] = None,
                      command: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get audit logs with optional filters

        Args:
            guild_id: Discord guild ID
            limit: Maximum number of logs to return
            user_id: Filter by user ID (optional)
            command: Filter by command name (optional)

        Returns:
            List of audit log dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM audit_logs WHERE guild_id = ?'
            params = [guild_id]

            if user_id:
                query += ' AND user_id = ?'
                params.append(user_id)

            if command:
                query += ' AND command = ?'
                params.append(command)

            query += ' ORDER BY executed_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting audit logs: {e}")
            return []
        finally:
            conn.close()

    def clear_old_audit_logs(self, days: int = 30) -> int:
        """
        Clear audit logs older than specified days

        Args:
            days: Number of days to keep logs

        Returns:
            Number of deleted records
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM audit_logs
                WHERE executed_at < datetime('now', '-' || ? || ' days')
            ''', (days,))

            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleared {deleted_count} old audit logs")
            return deleted_count

        except sqlite3.Error as e:
            logger.error(f"Error clearing old audit logs: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    # ==================== STATISTICS METHODS ====================

    def update_stats(self, guild_id: str, songs_played: int = 0,
                    playtime: int = 0, skips: int = 0) -> bool:
        """
        Update bot statistics for today

        Args:
            guild_id: Discord guild ID
            songs_played: Number of songs played
            playtime: Total playtime in seconds
            skips: Number of songs skipped

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO bot_stats (guild_id, songs_played, total_playtime, total_skips)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, date) DO UPDATE SET
                    songs_played = songs_played + ?,
                    total_playtime = total_playtime + ?,
                    total_skips = total_skips + ?
            ''', (guild_id, songs_played, playtime, skips,
                  songs_played, playtime, skips))

            conn.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Error updating stats for guild {guild_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_stats(self, guild_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get statistics for the last N days

        Args:
            guild_id: Discord guild ID
            days: Number of days to retrieve

        Returns:
            List of statistics dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM bot_stats
                WHERE guild_id = ?
                AND date >= date('now', '-' || ? || ' days')
                ORDER BY date DESC
            ''', (guild_id, days))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting stats for guild {guild_id}: {e}")
            return []
        finally:
            conn.close()

    def get_total_stats(self, guild_id: str) -> Optional[Dict[str, Any]]:
        """
        Get total accumulated statistics

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary with total statistics or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT
                    SUM(songs_played) as total_songs,
                    SUM(total_playtime) as total_playtime,
                    SUM(total_skips) as total_skips,
                    COUNT(DISTINCT date) as days_active
                FROM bot_stats
                WHERE guild_id = ?
            ''', (guild_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error getting total stats for guild {guild_id}: {e}")
            return None
        finally:
            conn.close()

    # ==================== UTILITY METHODS ====================

    def cleanup_orphaned_data(self) -> bool:
        """
        Clean up orphaned data (songs without playlists, etc.)
        This is a maintenance method to ensure data integrity

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Foreign keys should handle this, but this is a safety measure
            cursor.execute('''
                DELETE FROM songs
                WHERE playlist_id NOT IN (SELECT id FROM playlists)
            ''')

            deleted_songs = cursor.rowcount

            conn.commit()
            logger.info(f"Cleanup: Removed {deleted_songs} orphaned songs")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error during cleanup: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_database_stats(self) -> Dict[str, int]:
        """
        Get database statistics (record counts)

        Returns:
            Dictionary with table record counts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        stats = {}
        tables = ['servers', 'playlists', 'songs', 'user_favorites', 'audit_logs', 'bot_stats']

        try:
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                stats[table] = cursor.fetchone()[0]

            return stats

        except sqlite3.Error as e:
            logger.error(f"Error getting database stats: {e}")
            return {}
        finally:
            conn.close()

    def vacuum_database(self) -> bool:
        """
        Optimize database by reclaiming unused space

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()

        try:
            conn.execute('VACUUM')
            logger.info("Database vacuumed successfully")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error vacuuming database: {e}")
            return False
        finally:
            conn.close()


# Global database instance
db = Database()
