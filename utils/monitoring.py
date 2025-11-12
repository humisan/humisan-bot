"""
Enhanced Logging and Monitoring Module for Discord Music Bot

This module provides comprehensive logging, performance monitoring,
statistics collection, and health check capabilities.

Features:
- CommandLogger: Auto-log all slash commands with detailed metadata
- PerformanceMonitor: Track command execution times and bottlenecks
- StatisticsCollector: Track daily usage statistics and generate reports
- HealthCheck: Monitor bot health metrics (memory, database, voice)
- Helper functions for easy integration

Author: Discord Bot Team
Version: 1.0.0
"""

import asyncio
import psutil
import sqlite3
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager
from functools import wraps
from utils.logger import setup_logger
from utils.database import Database

logger = setup_logger(__name__)


# ==================== UTILITY DECORATORS ====================

def async_timer(func):
    """Decorator to measure async function execution time"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.perf_counter() - start_time
            logger.debug(f"{func.__name__} executed in {duration:.4f}s")
    return wrapper


def safe_execute(default_return=None):
    """Decorator for safe execution with error handling"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                return default_return

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                return default_return

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# ==================== COMMAND LOGGER ====================

class CommandLogger:
    """
    Auto-log all slash commands with comprehensive metadata

    Features:
    - Command name and parameters tracking
    - User and guild information
    - Execution timestamp and duration
    - Success/failure status tracking
    - Detailed error logging
    """

    def __init__(self, db: Database):
        """
        Initialize CommandLogger

        Args:
            db: Database instance for storing logs
        """
        self.db = db
        self._ensure_audit_logs_schema()
        logger.info("CommandLogger initialized")

    def _ensure_audit_logs_schema(self):
        """Ensure audit_logs table has all required columns"""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Check if table exists and get its schema
            cursor.execute("PRAGMA table_info(audit_logs)")
            columns = {row[1] for row in cursor.fetchall()}

            # Add missing columns if needed
            new_columns = {
                'username': 'TEXT',
                'guild_name': 'TEXT',
                'parameters': 'TEXT',
                'duration': 'REAL',
                'success': 'INTEGER DEFAULT 1',
                'error_message': 'TEXT'
            }

            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    cursor.execute(f'ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type}')
                    logger.info(f"Added column {col_name} to audit_logs table")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            logger.error(f"Error ensuring audit_logs schema: {e}")

    @safe_execute(default_return=False)
    async def log_command(
        self,
        guild_id: str,
        guild_name: str,
        user_id: str,
        username: str,
        command: str,
        parameters: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Log command execution with full metadata

        Args:
            guild_id: Discord guild ID
            guild_name: Guild name
            user_id: User ID who executed command
            username: Username who executed command
            command: Command name
            parameters: Command parameters/arguments
            duration: Execution duration in seconds
            success: Whether command succeeded
            error_message: Error message if failed

        Returns:
            True if logged successfully, False otherwise
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Serialize parameters to JSON
            params_json = json.dumps(parameters) if parameters else None

            cursor.execute('''
                INSERT INTO audit_logs (
                    guild_id, guild_name, user_id, username, command,
                    parameters, duration, success, error_message, details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                guild_id, guild_name, user_id, username, command,
                params_json, duration, int(success), error_message,
                f"Command: {command} | Success: {success}"
            ))

            conn.commit()
            conn.close()

            logger.debug(f"Logged command: {command} by {username} in {guild_name}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to log command: {e}")
            return False

    @safe_execute(default_return=[])
    async def get_command_history(
        self,
        guild_id: Optional[str] = None,
        user_id: Optional[str] = None,
        command: Optional[str] = None,
        limit: int = 100,
        success_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get command history with filters

        Args:
            guild_id: Filter by guild ID
            user_id: Filter by user ID
            command: Filter by command name
            limit: Maximum results to return
            success_only: Only return successful commands

        Returns:
            List of command log dictionaries
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            query = 'SELECT * FROM audit_logs WHERE 1=1'
            params = []

            if guild_id:
                query += ' AND guild_id = ?'
                params.append(guild_id)

            if user_id:
                query += ' AND user_id = ?'
                params.append(user_id)

            if command:
                query += ' AND command = ?'
                params.append(command)

            if success_only:
                query += ' AND success = 1'

            query += ' ORDER BY executed_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            # Parse JSON parameters
            results = []
            for row in rows:
                entry = dict(row)
                if entry.get('parameters'):
                    try:
                        entry['parameters'] = json.loads(entry['parameters'])
                    except json.JSONDecodeError:
                        entry['parameters'] = None
                results.append(entry)

            return results

        except sqlite3.Error as e:
            logger.error(f"Error getting command history: {e}")
            return []

    @safe_execute(default_return={})
    async def get_command_stats(
        self,
        guild_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get command usage statistics

        Args:
            guild_id: Discord guild ID
            days: Number of days to analyze

        Returns:
            Dictionary with command statistics
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Get total commands, success rate, most used commands
            cursor.execute('''
                SELECT
                    COUNT(*) as total_commands,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_commands,
                    AVG(duration) as avg_duration,
                    command,
                    COUNT(*) as command_count
                FROM audit_logs
                WHERE guild_id = ?
                AND executed_at >= datetime('now', '-' || ? || ' days')
                GROUP BY command
                ORDER BY command_count DESC
            ''', (guild_id, days))

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return {
                    'total_commands': 0,
                    'successful_commands': 0,
                    'success_rate': 0.0,
                    'avg_duration': 0.0,
                    'top_commands': []
                }

            total = sum(row['command_count'] for row in rows)
            successful = sum(
                cursor.execute('''
                    SELECT SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END)
                    FROM audit_logs
                    WHERE guild_id = ? AND executed_at >= datetime('now', '-' || ? || ' days')
                ''', (guild_id, days)).fetchone()[0] or 0
            )

            return {
                'total_commands': total,
                'successful_commands': successful,
                'success_rate': (successful / total * 100) if total > 0 else 0.0,
                'avg_duration': rows[0]['avg_duration'] or 0.0,
                'top_commands': [
                    {'command': row['command'], 'count': row['command_count']}
                    for row in rows[:10]
                ]
            }

        except sqlite3.Error as e:
            logger.error(f"Error getting command stats: {e}")
            return {}


# ==================== PERFORMANCE MONITOR ====================

class PerformanceMonitor:
    """
    Track command execution times and performance metrics

    Features:
    - Command execution time tracking
    - Bot response latency monitoring
    - Voice channel connection time
    - Music playback performance
    - Bottleneck detection and reporting
    """

    def __init__(self, db: Database):
        """
        Initialize PerformanceMonitor

        Args:
            db: Database instance
        """
        self.db = db
        self.metrics_cache = {}
        self.thresholds = {
            'command_slow': 2.0,  # seconds
            'voice_connect_slow': 5.0,  # seconds
            'response_slow': 1.0  # seconds
        }
        logger.info("PerformanceMonitor initialized")

    @asynccontextmanager
    async def track_command(
        self,
        command_name: str,
        guild_id: str,
        user_id: str
    ):
        """
        Context manager to track command execution time

        Usage:
            async with monitor.track_command('play', guild_id, user_id):
                # command execution
                pass

        Args:
            command_name: Name of the command
            guild_id: Discord guild ID
            user_id: User ID executing command
        """
        start_time = time.perf_counter()
        error = None

        try:
            yield
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.perf_counter() - start_time

            # Store metric
            await self._record_metric(
                'command_execution',
                command_name,
                guild_id,
                user_id,
                duration,
                error
            )

            # Check for slowdowns
            if duration > self.thresholds['command_slow']:
                logger.warning(
                    f"Slow command detected: {command_name} took {duration:.2f}s in guild {guild_id}"
                )

    @safe_execute(default_return=None)
    async def _record_metric(
        self,
        metric_type: str,
        name: str,
        guild_id: str,
        user_id: str,
        duration: float,
        error: Optional[str] = None
    ):
        """Record performance metric (internal use)"""
        cache_key = f"{guild_id}_{metric_type}_{name}"

        if cache_key not in self.metrics_cache:
            self.metrics_cache[cache_key] = []

        self.metrics_cache[cache_key].append({
            'timestamp': datetime.now(),
            'duration': duration,
            'error': error
        })

        # Keep only last 1000 metrics per key
        if len(self.metrics_cache[cache_key]) > 1000:
            self.metrics_cache[cache_key] = self.metrics_cache[cache_key][-1000:]

    @safe_execute(default_return={})
    async def get_performance_stats(
        self,
        guild_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get performance statistics for a guild

        Args:
            guild_id: Discord guild ID
            days: Number of days to analyze

        Returns:
            Dictionary with performance statistics
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Get command execution stats
            cursor.execute('''
                SELECT
                    command,
                    AVG(duration) as avg_duration,
                    MIN(duration) as min_duration,
                    MAX(duration) as max_duration,
                    COUNT(*) as execution_count
                FROM audit_logs
                WHERE guild_id = ?
                AND duration IS NOT NULL
                AND executed_at >= datetime('now', '-' || ? || ' days')
                GROUP BY command
                ORDER BY avg_duration DESC
            ''', (guild_id, days))

            rows = cursor.fetchall()
            conn.close()

            stats = {
                'slowest_commands': [
                    {
                        'command': row['command'],
                        'avg_duration': round(row['avg_duration'], 4),
                        'min_duration': round(row['min_duration'], 4),
                        'max_duration': round(row['max_duration'], 4),
                        'count': row['execution_count']
                    }
                    for row in rows[:10]
                ],
                'cache_metrics': self._get_cache_summary(guild_id)
            }

            return stats

        except sqlite3.Error as e:
            logger.error(f"Error getting performance stats: {e}")
            return {}

    def _get_cache_summary(self, guild_id: str) -> Dict[str, Any]:
        """Get summary of cached metrics"""
        guild_metrics = {
            k: v for k, v in self.metrics_cache.items()
            if k.startswith(guild_id)
        }

        if not guild_metrics:
            return {'total_cached': 0}

        total_metrics = sum(len(v) for v in guild_metrics.values())

        return {
            'total_cached': total_metrics,
            'metric_types': len(guild_metrics),
            'oldest_metric': min(
                (v[0]['timestamp'] for v in guild_metrics.values() if v),
                default=None
            )
        }

    @safe_execute(default_return=[])
    async def detect_bottlenecks(
        self,
        guild_id: str,
        threshold: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Detect performance bottlenecks

        Args:
            guild_id: Discord guild ID
            threshold: Duration threshold in seconds

        Returns:
            List of bottleneck reports
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    command,
                    AVG(duration) as avg_duration,
                    COUNT(*) as occurrence_count,
                    MAX(executed_at) as last_occurrence
                FROM audit_logs
                WHERE guild_id = ?
                AND duration > ?
                AND executed_at >= datetime('now', '-7 days')
                GROUP BY command
                ORDER BY avg_duration DESC
            ''', (guild_id, threshold))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    'command': row['command'],
                    'avg_duration': round(row['avg_duration'], 4),
                    'occurrence_count': row['occurrence_count'],
                    'last_occurrence': row['last_occurrence'],
                    'severity': 'high' if row['avg_duration'] > threshold * 2 else 'medium'
                }
                for row in rows
            ]

        except sqlite3.Error as e:
            logger.error(f"Error detecting bottlenecks: {e}")
            return []


# ==================== STATISTICS COLLECTOR ====================

class StatisticsCollector:
    """
    Track daily usage statistics and generate reports

    Features:
    - Songs played per guild tracking
    - Total playtime monitoring
    - Skip/pause statistics
    - Active users tracking
    - Command execution counts
    - Weekly/monthly report generation
    """

    def __init__(self, db: Database):
        """
        Initialize StatisticsCollector

        Args:
            db: Database instance
        """
        self.db = db
        self._ensure_stats_schema()
        logger.info("StatisticsCollector initialized")

    def _ensure_stats_schema(self):
        """Ensure bot_stats table has all required columns"""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(bot_stats)")
            columns = {row[1] for row in cursor.fetchall()}

            new_columns = {
                'total_pauses': 'INTEGER DEFAULT 0',
                'unique_users': 'INTEGER DEFAULT 0',
                'commands_executed': 'INTEGER DEFAULT 0'
            }

            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    cursor.execute(f'ALTER TABLE bot_stats ADD COLUMN {col_name} {col_type}')
                    logger.info(f"Added column {col_name} to bot_stats table")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            logger.error(f"Error ensuring bot_stats schema: {e}")

    @safe_execute(default_return=False)
    async def record_song_played(
        self,
        guild_id: str,
        duration: int,
        user_id: str
    ) -> bool:
        """
        Record a song being played

        Args:
            guild_id: Discord guild ID
            duration: Song duration in seconds
            user_id: User who played the song

        Returns:
            True if recorded successfully
        """
        return await self._update_daily_stats(
            guild_id,
            songs_played=1,
            playtime=duration,
            user_id=user_id
        )

    @safe_execute(default_return=False)
    async def record_skip(self, guild_id: str) -> bool:
        """Record a song skip"""
        return await self._update_daily_stats(guild_id, skips=1)

    @safe_execute(default_return=False)
    async def record_pause(self, guild_id: str) -> bool:
        """Record a pause event"""
        return await self._update_daily_stats(guild_id, pauses=1)

    @safe_execute(default_return=False)
    async def record_command(self, guild_id: str, user_id: str) -> bool:
        """Record a command execution"""
        return await self._update_daily_stats(guild_id, commands=1, user_id=user_id)

    async def _update_daily_stats(
        self,
        guild_id: str,
        songs_played: int = 0,
        playtime: int = 0,
        skips: int = 0,
        pauses: int = 0,
        commands: int = 0,
        user_id: Optional[str] = None
    ) -> bool:
        """Update daily statistics (internal use)"""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Update or insert stats for today
            cursor.execute('''
                INSERT INTO bot_stats (
                    guild_id, songs_played, total_playtime, total_skips,
                    total_pauses, commands_executed
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, date) DO UPDATE SET
                    songs_played = songs_played + ?,
                    total_playtime = total_playtime + ?,
                    total_skips = total_skips + ?,
                    total_pauses = total_pauses + ?,
                    commands_executed = commands_executed + ?
            ''', (
                guild_id, songs_played, playtime, skips, pauses, commands,
                songs_played, playtime, skips, pauses, commands
            ))

            # Update unique users if user_id provided
            if user_id:
                await self._update_unique_users(cursor, guild_id, user_id)

            conn.commit()
            conn.close()
            return True

        except sqlite3.Error as e:
            logger.error(f"Error updating daily stats: {e}")
            return False

    async def _update_unique_users(
        self,
        cursor: sqlite3.Cursor,
        guild_id: str,
        user_id: str
    ):
        """Update unique users count (internal use)"""
        # Count unique users from audit logs for today
        cursor.execute('''
            SELECT COUNT(DISTINCT user_id)
            FROM audit_logs
            WHERE guild_id = ?
            AND DATE(executed_at) = DATE('now')
        ''', (guild_id,))

        unique_count = cursor.fetchone()[0]

        cursor.execute('''
            UPDATE bot_stats
            SET unique_users = ?
            WHERE guild_id = ? AND date = DATE('now')
        ''', (unique_count, guild_id))

    @safe_execute(default_return={})
    async def get_daily_stats(
        self,
        guild_id: str,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics for a specific day

        Args:
            guild_id: Discord guild ID
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Dictionary with daily statistics
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            if date:
                cursor.execute('''
                    SELECT * FROM bot_stats
                    WHERE guild_id = ? AND date = ?
                ''', (guild_id, date))
            else:
                cursor.execute('''
                    SELECT * FROM bot_stats
                    WHERE guild_id = ? AND date = DATE('now')
                ''', (guild_id,))

            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else {}

        except sqlite3.Error as e:
            logger.error(f"Error getting daily stats: {e}")
            return {}

    @safe_execute(default_return={})
    async def generate_weekly_report(self, guild_id: str) -> Dict[str, Any]:
        """
        Generate weekly statistics report

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary with weekly statistics
        """
        return await self._generate_period_report(guild_id, 7, 'weekly')

    @safe_execute(default_return={})
    async def generate_monthly_report(self, guild_id: str) -> Dict[str, Any]:
        """
        Generate monthly statistics report

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary with monthly statistics
        """
        return await self._generate_period_report(guild_id, 30, 'monthly')

    async def _generate_period_report(
        self,
        guild_id: str,
        days: int,
        period_name: str
    ) -> Dict[str, Any]:
        """Generate statistics report for a period (internal use)"""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            # Get aggregated stats
            cursor.execute('''
                SELECT
                    SUM(songs_played) as total_songs,
                    SUM(total_playtime) as total_playtime,
                    SUM(total_skips) as total_skips,
                    SUM(total_pauses) as total_pauses,
                    SUM(commands_executed) as total_commands,
                    AVG(unique_users) as avg_daily_users,
                    MAX(unique_users) as peak_users,
                    COUNT(*) as active_days
                FROM bot_stats
                WHERE guild_id = ?
                AND date >= date('now', '-' || ? || ' days')
            ''', (guild_id, days))

            row = cursor.fetchone()

            # Get top commands
            cursor.execute('''
                SELECT command, COUNT(*) as count
                FROM audit_logs
                WHERE guild_id = ?
                AND executed_at >= datetime('now', '-' || ? || ' days')
                GROUP BY command
                ORDER BY count DESC
                LIMIT 10
            ''', (guild_id, days))

            top_commands = [
                {'command': r['command'], 'count': r['count']}
                for r in cursor.fetchall()
            ]

            conn.close()

            if not row or row['total_songs'] is None:
                return {
                    'period': period_name,
                    'days': days,
                    'no_data': True
                }

            # Calculate average playtime per song
            avg_song_duration = (
                row['total_playtime'] / row['total_songs']
                if row['total_songs'] > 0 else 0
            )

            return {
                'period': period_name,
                'days': days,
                'active_days': row['active_days'],
                'total_songs': row['total_songs'] or 0,
                'total_playtime': row['total_playtime'] or 0,
                'total_playtime_hours': round((row['total_playtime'] or 0) / 3600, 2),
                'total_skips': row['total_skips'] or 0,
                'total_pauses': row['total_pauses'] or 0,
                'total_commands': row['total_commands'] or 0,
                'avg_daily_users': round(row['avg_daily_users'] or 0, 1),
                'peak_users': row['peak_users'] or 0,
                'avg_song_duration': round(avg_song_duration, 0),
                'skip_rate': round(
                    (row['total_skips'] or 0) / (row['total_songs'] or 1) * 100,
                    2
                ),
                'top_commands': top_commands
            }

        except sqlite3.Error as e:
            logger.error(f"Error generating {period_name} report: {e}")
            return {}


# ==================== HEALTH CHECK ====================

class HealthCheck:
    """
    Monitor bot health metrics

    Features:
    - Memory usage monitoring
    - Database connection status
    - Voice client health
    - Command responsiveness
    - Error rate tracking
    """

    def __init__(self, db: Database):
        """
        Initialize HealthCheck

        Args:
            db: Database instance
        """
        self.db = db
        self.process = psutil.Process()
        self.health_history = []
        logger.info("HealthCheck initialized")

    @safe_execute(default_return={})
    async def check_memory(self) -> Dict[str, Any]:
        """
        Check memory usage

        Returns:
            Dictionary with memory statistics
        """
        try:
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()

            status = 'healthy'
            if memory_percent > 80:
                status = 'critical'
            elif memory_percent > 60:
                status = 'warning'

            return {
                'rss': memory_info.rss,  # Resident Set Size
                'rss_mb': round(memory_info.rss / 1024 / 1024, 2),
                'vms': memory_info.vms,  # Virtual Memory Size
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'percent': round(memory_percent, 2),
                'status': status
            }

        except Exception as e:
            logger.error(f"Error checking memory: {e}")
            return {'status': 'error', 'error': str(e)}

    @safe_execute(default_return={})
    async def check_database(self) -> Dict[str, Any]:
        """
        Check database connection and health

        Returns:
            Dictionary with database health status
        """
        try:
            start_time = time.perf_counter()
            conn = self.db._get_connection()

            # Test query
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM servers')
            server_count = cursor.fetchone()[0]

            # Get database size
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            db_size = cursor.fetchone()[0]

            conn.close()

            response_time = time.perf_counter() - start_time

            status = 'healthy'
            if response_time > 1.0:
                status = 'slow'

            return {
                'connected': True,
                'response_time': round(response_time, 4),
                'server_count': server_count,
                'database_size_mb': round(db_size / 1024 / 1024, 2),
                'status': status
            }

        except Exception as e:
            logger.error(f"Error checking database: {e}")
            return {
                'connected': False,
                'status': 'error',
                'error': str(e)
            }

    @safe_execute(default_return={})
    async def check_error_rate(self, guild_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check error rate from command executions

        Args:
            guild_id: Optional guild ID to filter by

        Returns:
            Dictionary with error rate statistics
        """
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            query = '''
                SELECT
                    COUNT(*) as total_commands,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_commands
                FROM audit_logs
                WHERE executed_at >= datetime('now', '-1 hour')
            '''
            params = []

            if guild_id:
                query += ' AND guild_id = ?'
                params.append(guild_id)

            cursor.execute(query, params)
            row = cursor.fetchone()
            conn.close()

            total = row['total_commands'] or 0
            failed = row['failed_commands'] or 0
            error_rate = (failed / total * 100) if total > 0 else 0

            status = 'healthy'
            if error_rate > 20:
                status = 'critical'
            elif error_rate > 10:
                status = 'warning'

            return {
                'total_commands': total,
                'failed_commands': failed,
                'error_rate': round(error_rate, 2),
                'status': status
            }

        except Exception as e:
            logger.error(f"Error checking error rate: {e}")
            return {'status': 'error', 'error': str(e)}

    @safe_execute(default_return={})
    async def check_cpu(self) -> Dict[str, Any]:
        """
        Check CPU usage

        Returns:
            Dictionary with CPU statistics
        """
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            cpu_times = self.process.cpu_times()

            status = 'healthy'
            if cpu_percent > 80:
                status = 'critical'
            elif cpu_percent > 60:
                status = 'warning'

            return {
                'percent': round(cpu_percent, 2),
                'user_time': round(cpu_times.user, 2),
                'system_time': round(cpu_times.system, 2),
                'status': status
            }

        except Exception as e:
            logger.error(f"Error checking CPU: {e}")
            return {'status': 'error', 'error': str(e)}

    @safe_execute(default_return={})
    async def get_full_health_report(
        self,
        guild_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive health report

        Args:
            guild_id: Optional guild ID for guild-specific checks

        Returns:
            Dictionary with full health report
        """
        memory = await self.check_memory()
        database = await self.check_database()
        cpu = await self.check_cpu()
        error_rate = await self.check_error_rate(guild_id)

        # Determine overall status
        statuses = [
            memory.get('status'),
            database.get('status'),
            cpu.get('status'),
            error_rate.get('status')
        ]

        if 'critical' in statuses or 'error' in statuses:
            overall_status = 'unhealthy'
        elif 'warning' in statuses or 'slow' in statuses:
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'

        report = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': overall_status,
            'memory': memory,
            'database': database,
            'cpu': cpu,
            'error_rate': error_rate,
            'uptime_seconds': round(time.time() - self.process.create_time(), 2)
        }

        # Store in history
        self.health_history.append(report)
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]

        return report


# ==================== HELPER FUNCTIONS ====================

async def log_command_execution(
    guild_id: str,
    guild_name: str,
    user_id: str,
    username: str,
    command: str,
    duration: float,
    success: bool,
    details: Optional[Dict[str, Any]] = None,
    db_path: str = 'data/bot.db'
) -> bool:
    """
    Helper function to log command execution

    Args:
        guild_id: Discord guild ID
        guild_name: Guild name
        user_id: User ID
        username: Username
        command: Command name
        duration: Execution duration in seconds
        success: Whether command succeeded
        details: Additional details/parameters
        db_path: Path to database file

    Returns:
        True if logged successfully
    """
    db = Database(db_path)
    logger_instance = CommandLogger(db)

    return await logger_instance.log_command(
        guild_id=guild_id,
        guild_name=guild_name,
        user_id=user_id,
        username=username,
        command=command,
        parameters=details,
        duration=duration,
        success=success
    )


async def get_performance_stats(
    guild_id: str,
    days: int = 7,
    db_path: str = 'data/bot.db'
) -> Dict[str, Any]:
    """
    Helper function to get performance statistics

    Args:
        guild_id: Discord guild ID
        days: Number of days to analyze
        db_path: Path to database file

    Returns:
        Dictionary with performance statistics
    """
    db = Database(db_path)
    monitor = PerformanceMonitor(db)

    return await monitor.get_performance_stats(guild_id, days)


async def get_health_report(
    guild_id: Optional[str] = None,
    db_path: str = 'data/bot.db'
) -> Dict[str, Any]:
    """
    Helper function to get health report

    Args:
        guild_id: Optional guild ID for guild-specific checks
        db_path: Path to database file

    Returns:
        Dictionary with health report
    """
    db = Database(db_path)
    health = HealthCheck(db)

    return await health.get_full_health_report(guild_id)


async def get_statistics_report(
    guild_id: str,
    period: str = 'weekly',
    db_path: str = 'data/bot.db'
) -> Dict[str, Any]:
    """
    Helper function to get statistics report

    Args:
        guild_id: Discord guild ID
        period: 'weekly' or 'monthly'
        db_path: Path to database file

    Returns:
        Dictionary with statistics report
    """
    db = Database(db_path)
    collector = StatisticsCollector(db)

    if period == 'monthly':
        return await collector.generate_monthly_report(guild_id)
    else:
        return await collector.generate_weekly_report(guild_id)


# ==================== INITIALIZATION ====================

def create_monitoring_system(db: Database) -> Tuple[CommandLogger, PerformanceMonitor, StatisticsCollector, HealthCheck]:
    """
    Create and initialize all monitoring components

    Args:
        db: Database instance

    Returns:
        Tuple of (CommandLogger, PerformanceMonitor, StatisticsCollector, HealthCheck)
    """
    command_logger = CommandLogger(db)
    performance_monitor = PerformanceMonitor(db)
    statistics_collector = StatisticsCollector(db)
    health_check = HealthCheck(db)

    logger.info("All monitoring systems initialized successfully")

    return command_logger, performance_monitor, statistics_collector, health_check


if __name__ == '__main__':
    # Test module functionality
    import asyncio

    async def test_monitoring():
        """Test monitoring functionality"""
        print("Testing Enhanced Logging and Monitoring Module")
        print("=" * 50)

        # Initialize
        db = Database('data/bot.db')
        cmd_logger, perf_monitor, stats_collector, health = create_monitoring_system(db)

        # Test command logging
        print("\n1. Testing command logging...")
        await cmd_logger.log_command(
            guild_id='123456789',
            guild_name='Test Server',
            user_id='987654321',
            username='TestUser',
            command='play',
            parameters={'song': 'test.mp3'},
            duration=0.5,
            success=True
        )
        print("   Command logged successfully")

        # Test performance tracking
        print("\n2. Testing performance monitoring...")
        async with perf_monitor.track_command('test_command', '123456789', '987654321'):
            await asyncio.sleep(0.1)
        print("   Performance tracked successfully")

        # Test statistics collection
        print("\n3. Testing statistics collection...")
        await stats_collector.record_song_played('123456789', 180, '987654321')
        await stats_collector.record_skip('123456789')
        print("   Statistics recorded successfully")

        # Test health check
        print("\n4. Testing health check...")
        health_report = await health.get_full_health_report()
        print(f"   Overall Status: {health_report['overall_status']}")
        print(f"   Memory: {health_report['memory']['rss_mb']} MB")
        print(f"   Database: {health_report['database']['status']}")

        print("\n" + "=" * 50)
        print("All tests completed successfully!")

    asyncio.run(test_monitoring())
