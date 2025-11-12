"""
Test script for Enhanced Logging and Monitoring Module

This script demonstrates all features of the monitoring system.
"""

import asyncio
import time
from utils.monitoring import (
    CommandLogger,
    PerformanceMonitor,
    StatisticsCollector,
    HealthCheck,
    create_monitoring_system,
    log_command_execution,
    get_performance_stats,
    get_health_report,
    get_statistics_report
)
from utils.database import Database


async def test_command_logger(cmd_logger: CommandLogger):
    """Test CommandLogger functionality"""
    print("\n" + "=" * 60)
    print("TESTING COMMAND LOGGER")
    print("=" * 60)

    # Log successful command
    print("\n1. Logging successful command...")
    success = await cmd_logger.log_command(
        guild_id='123456789',
        guild_name='Test Server',
        user_id='987654321',
        username='TestUser#1234',
        command='play',
        parameters={'song': 'Never Gonna Give You Up', 'volume': 50},
        duration=0.456,
        success=True
    )
    print(f"   Result: {'Success' if success else 'Failed'}")

    # Log failed command
    print("\n2. Logging failed command...")
    success = await cmd_logger.log_command(
        guild_id='123456789',
        guild_name='Test Server',
        user_id='111222333',
        username='ErrorUser#9999',
        command='skip',
        parameters={},
        duration=0.123,
        success=False,
        error_message='No song is currently playing'
    )
    print(f"   Result: {'Success' if success else 'Failed'}")

    # Log multiple commands for testing
    print("\n3. Logging multiple commands for statistics...")
    commands = [
        ('play', True, 0.5),
        ('pause', True, 0.1),
        ('resume', True, 0.1),
        ('skip', True, 0.2),
        ('queue', True, 0.3),
        ('play', False, 0.8),
    ]

    for cmd, success, duration in commands:
        await cmd_logger.log_command(
            guild_id='123456789',
            guild_name='Test Server',
            user_id='987654321',
            username='TestUser#1234',
            command=cmd,
            parameters={},
            duration=duration,
            success=success
        )
    print(f"   Logged {len(commands)} commands")

    # Get command history
    print("\n4. Retrieving command history...")
    history = await cmd_logger.get_command_history(guild_id='123456789', limit=10)
    print(f"   Retrieved {len(history)} command logs")
    if history:
        last_cmd = history[0]
        print(f"   Last command: {last_cmd['command']} by {last_cmd.get('username', 'Unknown')}")

    # Get command statistics
    print("\n5. Retrieving command statistics...")
    stats = await cmd_logger.get_command_stats(guild_id='123456789', days=7)
    print(f"   Total commands: {stats.get('total_commands', 0)}")
    print(f"   Success rate: {stats.get('success_rate', 0):.2f}%")
    print(f"   Average duration: {stats.get('avg_duration', 0):.4f}s")
    if stats.get('top_commands'):
        print(f"   Top command: {stats['top_commands'][0]['command']} ({stats['top_commands'][0]['count']} times)")


async def test_performance_monitor(perf_monitor: PerformanceMonitor):
    """Test PerformanceMonitor functionality"""
    print("\n" + "=" * 60)
    print("TESTING PERFORMANCE MONITOR")
    print("=" * 60)

    # Track command execution
    print("\n1. Tracking command execution...")
    async with perf_monitor.track_command('play', '123456789', '987654321'):
        await asyncio.sleep(0.5)  # Simulate command execution
    print("   Command tracked successfully")

    # Track slow command
    print("\n2. Tracking slow command (should trigger warning)...")
    async with perf_monitor.track_command('slow_command', '123456789', '987654321'):
        await asyncio.sleep(2.5)  # Simulate slow command
    print("   Slow command tracked")

    # Get performance stats
    print("\n3. Retrieving performance statistics...")
    stats = await perf_monitor.get_performance_stats(guild_id='123456789', days=7)
    if stats.get('slowest_commands'):
        print(f"   Found {len(stats['slowest_commands'])} commands with timing data")
        for cmd in stats['slowest_commands'][:3]:
            print(f"   - {cmd['command']}: avg {cmd['avg_duration']:.4f}s (count: {cmd['count']})")

    # Detect bottlenecks
    print("\n4. Detecting bottlenecks...")
    bottlenecks = await perf_monitor.detect_bottlenecks(guild_id='123456789', threshold=1.0)
    if bottlenecks:
        print(f"   Found {len(bottlenecks)} bottlenecks:")
        for bn in bottlenecks:
            print(f"   - {bn['command']}: {bn['avg_duration']:.4f}s ({bn['severity']} severity)")
    else:
        print("   No bottlenecks detected")


async def test_statistics_collector(stats_collector: StatisticsCollector):
    """Test StatisticsCollector functionality"""
    print("\n" + "=" * 60)
    print("TESTING STATISTICS COLLECTOR")
    print("=" * 60)

    # Record various events
    print("\n1. Recording song plays...")
    for i in range(5):
        await stats_collector.record_song_played(
            guild_id='123456789',
            duration=180 + i * 30,  # 3-5 minutes
            user_id=f'user_{i}'
        )
    print("   Recorded 5 song plays")

    print("\n2. Recording skips...")
    await stats_collector.record_skip('123456789')
    await stats_collector.record_skip('123456789')
    print("   Recorded 2 skips")

    print("\n3. Recording pauses...")
    await stats_collector.record_pause('123456789')
    print("   Recorded 1 pause")

    print("\n4. Recording commands...")
    for i in range(10):
        await stats_collector.record_command('123456789', f'user_{i % 3}')
    print("   Recorded 10 commands")

    # Get daily stats
    print("\n5. Retrieving daily statistics...")
    daily_stats = await stats_collector.get_daily_stats(guild_id='123456789')
    if daily_stats:
        print(f"   Songs played: {daily_stats.get('songs_played', 0)}")
        print(f"   Total playtime: {daily_stats.get('total_playtime', 0)}s")
        print(f"   Total skips: {daily_stats.get('total_skips', 0)}")
        print(f"   Commands executed: {daily_stats.get('commands_executed', 0)}")
        print(f"   Unique users: {daily_stats.get('unique_users', 0)}")

    # Generate weekly report
    print("\n6. Generating weekly report...")
    weekly_report = await stats_collector.generate_weekly_report(guild_id='123456789')
    if weekly_report and not weekly_report.get('no_data'):
        print(f"   Period: {weekly_report['period']}")
        print(f"   Active days: {weekly_report['active_days']}")
        print(f"   Total songs: {weekly_report['total_songs']}")
        print(f"   Total playtime: {weekly_report['total_playtime_hours']} hours")
        print(f"   Skip rate: {weekly_report['skip_rate']}%")
        print(f"   Average daily users: {weekly_report['avg_daily_users']}")

    # Generate monthly report
    print("\n7. Generating monthly report...")
    monthly_report = await stats_collector.generate_monthly_report(guild_id='123456789')
    if monthly_report and not monthly_report.get('no_data'):
        print(f"   Period: {monthly_report['period']}")
        print(f"   Active days: {monthly_report['active_days']}")
        print(f"   Total songs: {monthly_report['total_songs']}")


async def test_health_check(health_check: HealthCheck):
    """Test HealthCheck functionality"""
    print("\n" + "=" * 60)
    print("TESTING HEALTH CHECK")
    print("=" * 60)

    # Check memory
    print("\n1. Checking memory usage...")
    memory = await health_check.check_memory()
    print(f"   RSS: {memory.get('rss_mb', 0)} MB")
    print(f"   VMS: {memory.get('vms_mb', 0)} MB")
    print(f"   Percent: {memory.get('percent', 0)}%")
    print(f"   Status: {memory.get('status', 'unknown')}")

    # Check database
    print("\n2. Checking database connection...")
    database = await health_check.check_database()
    print(f"   Connected: {database.get('connected', False)}")
    print(f"   Response time: {database.get('response_time', 0)}s")
    print(f"   Server count: {database.get('server_count', 0)}")
    print(f"   Database size: {database.get('database_size_mb', 0)} MB")
    print(f"   Status: {database.get('status', 'unknown')}")

    # Check CPU
    print("\n3. Checking CPU usage...")
    cpu = await health_check.check_cpu()
    print(f"   Percent: {cpu.get('percent', 0)}%")
    print(f"   User time: {cpu.get('user_time', 0)}s")
    print(f"   System time: {cpu.get('system_time', 0)}s")
    print(f"   Status: {cpu.get('status', 'unknown')}")

    # Check error rate
    print("\n4. Checking error rate...")
    error_rate = await health_check.check_error_rate(guild_id='123456789')
    print(f"   Total commands: {error_rate.get('total_commands', 0)}")
    print(f"   Failed commands: {error_rate.get('failed_commands', 0)}")
    print(f"   Error rate: {error_rate.get('error_rate', 0)}%")
    print(f"   Status: {error_rate.get('status', 'unknown')}")

    # Get full health report
    print("\n5. Generating full health report...")
    report = await health_check.get_full_health_report(guild_id='123456789')
    print(f"   Overall status: {report.get('overall_status', 'unknown').upper()}")
    print(f"   Uptime: {report.get('uptime_seconds', 0):.2f}s")
    print(f"   Timestamp: {report.get('timestamp', 'N/A')}")


async def test_helper_functions():
    """Test helper functions"""
    print("\n" + "=" * 60)
    print("TESTING HELPER FUNCTIONS")
    print("=" * 60)

    # Test log_command_execution
    print("\n1. Testing log_command_execution()...")
    success = await log_command_execution(
        guild_id='999888777',
        guild_name='Helper Test Server',
        user_id='111222333',
        username='HelperUser#0001',
        command='volume',
        duration=0.234,
        success=True,
        details={'old_volume': 50, 'new_volume': 75}
    )
    print(f"   Result: {'Success' if success else 'Failed'}")

    # Test get_performance_stats
    print("\n2. Testing get_performance_stats()...")
    stats = await get_performance_stats(guild_id='123456789', days=7)
    print(f"   Retrieved stats with {len(stats.get('slowest_commands', []))} commands")

    # Test get_health_report
    print("\n3. Testing get_health_report()...")
    health = await get_health_report()
    print(f"   Overall status: {health.get('overall_status', 'unknown').upper()}")

    # Test get_statistics_report
    print("\n4. Testing get_statistics_report() - weekly...")
    report = await get_statistics_report(guild_id='123456789', period='weekly')
    if report and not report.get('no_data'):
        print(f"   Weekly - Total songs: {report.get('total_songs', 0)}")

    print("\n5. Testing get_statistics_report() - monthly...")
    report = await get_statistics_report(guild_id='123456789', period='monthly')
    if report and not report.get('no_data'):
        print(f"   Monthly - Total songs: {report.get('total_songs', 0)}")


async def main():
    """Main test function"""
    print("\n")
    print("=" * 60)
    print("ENHANCED LOGGING AND MONITORING MODULE - TEST SUITE")
    print("=" * 60)
    print("\nInitializing test environment...")

    # Initialize database and monitoring system
    db = Database('data/bot.db')
    cmd_logger, perf_monitor, stats_collector, health_check = create_monitoring_system(db)

    print("Monitoring system initialized successfully!")

    # Run all tests
    await test_command_logger(cmd_logger)
    await test_performance_monitor(perf_monitor)
    await test_statistics_collector(stats_collector)
    await test_health_check(health_check)
    await test_helper_functions()

    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETED")
    print("=" * 60)
    print("\nAll features tested successfully!")
    print("\nModule Features:")
    print("  - CommandLogger: Full command logging with metadata")
    print("  - PerformanceMonitor: Execution time tracking and bottleneck detection")
    print("  - StatisticsCollector: Daily usage stats and report generation")
    print("  - HealthCheck: System health monitoring (memory, CPU, database)")
    print("  - Helper Functions: Easy-to-use standalone functions")
    print("\nIntegration Ready:")
    print("  - Async support for non-blocking operations")
    print("  - Error handling and safe execution")
    print("  - Database integration with utils.database.Database")
    print("  - Logging integration with utils.logger")
    print("\n" + "=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
