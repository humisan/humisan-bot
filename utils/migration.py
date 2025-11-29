import json
import os
import shutil
from typing import Dict, List, Any, Tuple
from datetime import datetime
from utils.database import Database
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MigrationReport:
    """Report class to track migration statistics"""

    def __init__(self):
        self.favorites_migrated = 0
        self.favorites_skipped = 0
        self.favorites_errors = 0
        self.playlists_migrated = 0
        self.playlists_skipped = 0
        self.songs_migrated = 0
        self.songs_skipped = 0
        self.songs_errors = 0
        self.servers_created = 0
        self.errors = []
        self.start_time = None
        self.end_time = None

    def add_error(self, error_msg: str):
        """Add an error message to the report"""
        self.errors.append(error_msg)
        logger.error(error_msg)

    def get_duration(self) -> float:
        """Calculate migration duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def get_summary(self) -> Dict[str, Any]:
        """Get migration summary as dictionary"""
        return {
            'servers_created': self.servers_created,
            'favorites': {
                'migrated': self.favorites_migrated,
                'skipped': self.favorites_skipped,
                'errors': self.favorites_errors
            },
            'playlists': {
                'created': self.playlists_migrated,
                'skipped': self.playlists_skipped
            },
            'songs': {
                'migrated': self.songs_migrated,
                'skipped': self.songs_skipped,
                'errors': self.songs_errors
            },
            'total_errors': len(self.errors),
            'duration_seconds': self.get_duration(),
            'errors': self.errors[:10]  # Include first 10 errors in summary
        }

    def print_summary(self):
        """Print formatted migration summary"""
        summary = self.get_summary()

        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Duration: {summary['duration_seconds']:.2f} seconds")
        print()
        print("SERVERS:")
        print(f"  Created: {summary['servers_created']}")
        print()
        print("FAVORITES:")
        print(f"  Migrated: {summary['favorites']['migrated']}")
        print(f"  Skipped (duplicates): {summary['favorites']['skipped']}")
        print(f"  Errors: {summary['favorites']['errors']}")
        print()
        print("PLAYLISTS:")
        print(f"  Created: {summary['playlists']['created']}")
        print(f"  Skipped (duplicates): {summary['playlists']['skipped']}")
        print()
        print("SONGS:")
        print(f"  Migrated: {summary['songs']['migrated']}")
        print(f"  Skipped (duplicates): {summary['songs']['skipped']}")
        print(f"  Errors: {summary['songs']['errors']}")
        print()
        print(f"Total Errors: {summary['total_errors']}")

        if summary['errors']:
            print("\nFirst 10 Errors:")
            for i, error in enumerate(summary['errors'], 1):
                print(f"  {i}. {error}")

        print("="*60)


class DataMigration:
    """Main migration class for migrating JSON data to database"""

    def __init__(self, db: Database, favorites_path: str = 'data/favorites.json',
                 playlists_path: str = 'data/playlists.json'):
        """
        Initialize migration

        Args:
            db: Database instance
            favorites_path: Path to favorites JSON file
            playlists_path: Path to playlists JSON file
        """
        self.db = db
        self.favorites_path = favorites_path
        self.playlists_path = playlists_path
        self.report = MigrationReport()

    def _create_backup(self, file_path: str) -> bool:
        """
        Create backup of JSON file before migration

        Args:
            file_path: Path to file to backup

        Returns:
            True if backup successful, False otherwise
        """
        if not os.path.exists(file_path):
            logger.warning(f"File not found for backup: {file_path}")
            return False

        try:
            backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return True
        except Exception as e:
            error_msg = f"Failed to create backup of {file_path}: {str(e)}"
            self.report.add_error(error_msg)
            return False

    def _load_json_file(self, file_path: str) -> Dict:
        """
        Load and parse JSON file

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON data or empty dict if error
        """
        if not os.path.exists(file_path):
            logger.warning(f"JSON file not found: {file_path}")
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded JSON file: {file_path}")
            return data
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in {file_path}: {str(e)}"
            self.report.add_error(error_msg)
            return {}
        except Exception as e:
            error_msg = f"Error loading {file_path}: {str(e)}"
            self.report.add_error(error_msg)
            return {}

    def _ensure_server_exists(self, guild_id: str) -> bool:
        """
        Ensure server exists in database

        Args:
            guild_id: Discord guild ID

        Returns:
            True if server exists or was created, False otherwise
        """
        # Check if server already exists
        existing = self.db.get_server_settings(guild_id)
        if existing:
            return True

        # Create new server entry
        success = self.db.create_server(
            guild_id=guild_id,
            guild_name=f"Server {guild_id}",  # Default name
            prefix='!',
            default_volume=50
        )

        if success:
            self.report.servers_created += 1
            logger.info(f"Created server entry for guild {guild_id}")
        else:
            error_msg = f"Failed to create server entry for guild {guild_id}"
            self.report.add_error(error_msg)

        return success

    def _check_favorite_exists(self, guild_id: str, user_id: str, url: str) -> bool:
        """
        Check if favorite already exists in database

        Args:
            guild_id: Discord guild ID
            user_id: User ID
            url: Song URL

        Returns:
            True if favorite exists, False otherwise
        """
        favorites = self.db.get_user_favorites(guild_id, user_id)
        return any(fav['url'] == url for fav in favorites)

    def migrate_favorites(self) -> Tuple[int, int, int]:
        """
        Migrate user favorites from JSON to database

        Returns:
            Tuple of (migrated, skipped, errors)
        """
        logger.info("Starting favorites migration...")

        # Create backup
        self._create_backup(self.favorites_path)

        # Load JSON data
        favorites_data = self._load_json_file(self.favorites_path)

        if not favorites_data:
            logger.warning("No favorites data to migrate")
            return (0, 0, 0)

        # Structure: {"guild_id": {"user_id": [songs]}}
        for guild_id, users in favorites_data.items():
            logger.info(f"Migrating favorites for guild {guild_id}")

            # Ensure server exists
            if not self._ensure_server_exists(guild_id):
                continue

            for user_id, songs in users.items():
                logger.info(f"  Processing {len(songs)} favorites for user {user_id}")

                for song in songs:
                    try:
                        # Validate required fields
                        if not song.get('title') or not song.get('url'):
                            error_msg = f"Invalid song data for user {user_id}: missing title or url"
                            self.report.add_error(error_msg)
                            self.report.favorites_errors += 1
                            continue

                        # Check if already exists
                        if self._check_favorite_exists(guild_id, user_id, song['url']):
                            logger.debug(f"    Skipping duplicate: {song['title']}")
                            self.report.favorites_skipped += 1
                            continue

                        # Add to database
                        result = self.db.add_favorite(
                            guild_id=guild_id,
                            user_id=user_id,
                            title=song.get('title'),
                            url=song.get('url'),
                            webpage_url=song.get('webpage_url'),
                            duration=song.get('duration'),
                            thumbnail=song.get('thumbnail')
                        )

                        if result:
                            self.report.favorites_migrated += 1
                            logger.debug(f"    Migrated: {song['title']}")
                        else:
                            # Could be duplicate caught by database
                            self.report.favorites_skipped += 1
                            logger.debug(f"    Skipped (DB constraint): {song['title']}")

                    except Exception as e:
                        error_msg = f"Error migrating favorite '{song.get('title', 'unknown')}': {str(e)}"
                        self.report.add_error(error_msg)
                        self.report.favorites_errors += 1

        logger.info(f"Favorites migration complete: {self.report.favorites_migrated} migrated, "
                   f"{self.report.favorites_skipped} skipped, {self.report.favorites_errors} errors")

        return (self.report.favorites_migrated, self.report.favorites_skipped,
                self.report.favorites_errors)

    def _check_playlist_exists(self, guild_id: str, playlist_name: str) -> bool:
        """
        Check if playlist already exists in database

        Args:
            guild_id: Discord guild ID
            playlist_name: Playlist name

        Returns:
            True if playlist exists, False otherwise
        """
        playlist = self.db.get_playlist_by_name(guild_id, playlist_name)
        return playlist is not None

    def _get_playlist_songs(self, playlist_id: int) -> List[str]:
        """
        Get list of song URLs in a playlist

        Args:
            playlist_id: Playlist ID

        Returns:
            List of song URLs
        """
        songs = self.db.get_songs_from_playlist(playlist_id)
        return [song['url'] for song in songs]

    def migrate_playlists(self) -> Tuple[int, int, int]:
        """
        Migrate playlists from JSON to database

        Returns:
            Tuple of (playlists_created, songs_migrated, songs_skipped)
        """
        logger.info("Starting playlists migration...")

        # Create backup
        self._create_backup(self.playlists_path)

        # Load JSON data
        playlists_data = self._load_json_file(self.playlists_path)

        if not playlists_data:
            logger.warning("No playlists data to migrate")
            return (0, 0, 0)

        # Structure: {"guild_id": {"playlist_name": [songs]}}
        for guild_id, playlists in playlists_data.items():
            logger.info(f"Migrating playlists for guild {guild_id}")

            # Ensure server exists
            if not self._ensure_server_exists(guild_id):
                continue

            for playlist_name, songs in playlists.items():
                logger.info(f"  Processing playlist '{playlist_name}' with {len(songs)} songs")

                try:
                    # Check if playlist already exists
                    playlist = self.db.get_playlist_by_name(guild_id, playlist_name)

                    if playlist:
                        logger.info(f"    Playlist '{playlist_name}' already exists")
                        self.report.playlists_skipped += 1
                        playlist_id = playlist['id']

                        # Get existing songs to check for duplicates
                        existing_urls = self._get_playlist_songs(playlist_id)
                    else:
                        # Create new playlist (use system user ID for migration)
                        playlist_id = self.db.create_playlist(
                            guild_id=guild_id,
                            name=playlist_name,
                            created_by='0'  # System user for migration
                        )

                        if not playlist_id:
                            error_msg = f"Failed to create playlist '{playlist_name}'"
                            self.report.add_error(error_msg)
                            continue

                        self.report.playlists_migrated += 1
                        logger.info(f"    Created playlist '{playlist_name}'")
                        existing_urls = []

                    # Migrate songs
                    for song in songs:
                        try:
                            # Validate required fields
                            if not song.get('title') or not song.get('url'):
                                error_msg = f"Invalid song data in playlist '{playlist_name}': missing title or url"
                                self.report.add_error(error_msg)
                                self.report.songs_errors += 1
                                continue

                            # Check if song already exists in playlist
                            if song['url'] in existing_urls:
                                logger.debug(f"      Skipping duplicate song: {song['title']}")
                                self.report.songs_skipped += 1
                                continue

                            # Add song to playlist
                            result = self.db.add_song_to_playlist(
                                playlist_id=playlist_id,
                                title=song.get('title'),
                                url=song.get('url'),
                                webpage_url=song.get('webpage_url'),
                                duration=song.get('duration'),
                                thumbnail=song.get('thumbnail'),
                                added_by='0'  # System user for migration
                            )

                            if result:
                                self.report.songs_migrated += 1
                                existing_urls.append(song['url'])
                                logger.debug(f"      Migrated song: {song['title']}")
                            else:
                                error_msg = f"Failed to add song '{song['title']}' to playlist '{playlist_name}'"
                                self.report.add_error(error_msg)
                                self.report.songs_errors += 1

                        except Exception as e:
                            error_msg = f"Error migrating song '{song.get('title', 'unknown')}': {str(e)}"
                            self.report.add_error(error_msg)
                            self.report.songs_errors += 1

                except Exception as e:
                    error_msg = f"Error processing playlist '{playlist_name}': {str(e)}"
                    self.report.add_error(error_msg)

        logger.info(f"Playlists migration complete: {self.report.playlists_migrated} created, "
                   f"{self.report.songs_migrated} songs migrated, {self.report.songs_skipped} songs skipped")

        return (self.report.playlists_migrated, self.report.songs_migrated,
                self.report.songs_skipped)

    def run_migration(self) -> MigrationReport:
        """
        Run complete migration process

        Returns:
            MigrationReport with summary of migration
        """
        logger.info("="*60)
        logger.info("STARTING DATA MIGRATION")
        logger.info("="*60)

        self.report.start_time = datetime.now()

        try:
            # Verify database connection
            logger.info("Verifying database connection...")
            stats = self.db.get_database_stats()
            logger.info(f"Database stats before migration: {stats}")

            # Migrate favorites
            logger.info("\n--- PHASE 1: Migrating Favorites ---")
            self.migrate_favorites()

            # Migrate playlists
            logger.info("\n--- PHASE 2: Migrating Playlists ---")
            self.migrate_playlists()

            # Final stats
            logger.info("\nVerifying migration results...")
            final_stats = self.db.get_database_stats()
            logger.info(f"Database stats after migration: {final_stats}")

        except Exception as e:
            error_msg = f"Critical error during migration: {str(e)}"
            self.report.add_error(error_msg)
            logger.exception("Migration failed with exception")

        finally:
            self.report.end_time = datetime.now()

        logger.info("\n" + "="*60)
        logger.info("MIGRATION COMPLETE")
        logger.info("="*60)

        return self.report


def run_migration(db: Database, favorites_path: str = 'data/favorites.json',
                  playlists_path: str = 'data/playlists.json') -> Dict[str, Any]:
    """
    Convenience function to run migration and return summary

    Args:
        db: Database instance
        favorites_path: Path to favorites JSON file
        playlists_path: Path to playlists JSON file

    Returns:
        Dictionary with migration summary
    """
    migration = DataMigration(db, favorites_path, playlists_path)
    report = migration.run_migration()

    # Return summary as dictionary (without printing detailed summary)
    return report.get_summary()


# Example usage
if __name__ == '__main__':
    """
    Example usage of migration script
    """
    # Initialize database
    db = Database('data/bot.db')

    # Run migration
    summary = run_migration(
        db=db,
        favorites_path='data/favorites.json',
        playlists_path='data/playlists.json'
    )

    # Access summary data
    print(f"\nTotal favorites migrated: {summary['favorites']['migrated']}")
    print(f"Total playlists created: {summary['playlists']['created']}")
    print(f"Total songs migrated: {summary['songs']['migrated']}")
    print(f"Migration duration: {summary['duration_seconds']:.2f} seconds")
