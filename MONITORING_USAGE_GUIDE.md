# Enhanced Logging and Monitoring Module - Usage Guide

## Overview

The enhanced logging and monitoring module (`utils/monitoring.py`) provides comprehensive tracking, performance monitoring, statistics collection, and health checking for your Discord music bot.

## Installation

The module requires `psutil` for system monitoring. Install dependencies:

```bash
pip install -r requirements.txt
```

## Features

### 1. CommandLogger

Automatically log all slash commands with comprehensive metadata.

#### Features:
- Command name and parameters
- User and guild information
- Execution timestamps and duration
- Success/failure status
- Detailed error logging

#### Usage:

```python
from utils.monitoring import CommandLogger
from utils.database import Database

# Initialize
db = Database('data/bot.db')
cmd_logger = CommandLogger(db)

# Log a command
await cmd_logger.log_command(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name,
    user_id=str(ctx.author.id),
    username=str(ctx.author),
    command='play',
    parameters={'song': song_name, 'volume': 50},
    duration=0.456,  # seconds
    success=True,
    error_message=None
)

# Get command history
history = await cmd_logger.get_command_history(
    guild_id=str(ctx.guild.id),
    limit=100
)

# Get command statistics
stats = await cmd_logger.get_command_stats(
    guild_id=str(ctx.guild.id),
    days=7
)
print(f"Success rate: {stats['success_rate']}%")
print(f"Top command: {stats['top_commands'][0]['command']}")
```

### 2. PerformanceMonitor

Track command execution times and detect performance bottlenecks.

#### Features:
- Command execution time tracking
- Response latency monitoring
- Automatic slowdown detection
- Bottleneck reporting

#### Usage:

```python
from utils.monitoring import PerformanceMonitor

# Initialize
perf_monitor = PerformanceMonitor(db)

# Track command execution with context manager
async with perf_monitor.track_command('play', str(ctx.guild.id), str(ctx.author.id)):
    # Your command code here
    await play_song(ctx, song)
# Duration is automatically tracked

# Get performance statistics
stats = await perf_monitor.get_performance_stats(
    guild_id=str(ctx.guild.id),
    days=7
)

# Detect bottlenecks
bottlenecks = await perf_monitor.detect_bottlenecks(
    guild_id=str(ctx.guild.id),
    threshold=2.0  # seconds
)

for bottleneck in bottlenecks:
    print(f"Slow command: {bottleneck['command']}")
    print(f"Average duration: {bottleneck['avg_duration']}s")
    print(f"Severity: {bottleneck['severity']}")
```

### 3. StatisticsCollector

Track daily usage statistics and generate reports.

#### Features:
- Songs played tracking
- Total playtime monitoring
- Skip/pause statistics
- Active users tracking
- Command execution counts
- Weekly/monthly reports

#### Usage:

```python
from utils.monitoring import StatisticsCollector

# Initialize
stats_collector = StatisticsCollector(db)

# Record events
await stats_collector.record_song_played(
    guild_id=str(ctx.guild.id),
    duration=180,  # seconds
    user_id=str(ctx.author.id)
)

await stats_collector.record_skip(str(ctx.guild.id))
await stats_collector.record_pause(str(ctx.guild.id))
await stats_collector.record_command(str(ctx.guild.id), str(ctx.author.id))

# Get daily statistics
daily_stats = await stats_collector.get_daily_stats(
    guild_id=str(ctx.guild.id)
)
print(f"Songs played today: {daily_stats['songs_played']}")
print(f"Unique users: {daily_stats['unique_users']}")

# Generate weekly report
weekly_report = await stats_collector.generate_weekly_report(
    guild_id=str(ctx.guild.id)
)
print(f"Total songs: {weekly_report['total_songs']}")
print(f"Playtime: {weekly_report['total_playtime_hours']} hours")
print(f"Skip rate: {weekly_report['skip_rate']}%")

# Generate monthly report
monthly_report = await stats_collector.generate_monthly_report(
    guild_id=str(ctx.guild.id)
)
```

### 4. HealthCheck

Monitor bot health and system resources.

#### Features:
- Memory usage monitoring
- CPU usage tracking
- Database connection status
- Error rate tracking
- Overall health reporting

#### Usage:

```python
from utils.monitoring import HealthCheck

# Initialize
health_check = HealthCheck(db)

# Check individual components
memory = await health_check.check_memory()
print(f"Memory usage: {memory['rss_mb']} MB ({memory['percent']}%)")

database = await health_check.check_database()
print(f"Database status: {database['status']}")
print(f"Response time: {database['response_time']}s")

cpu = await health_check.check_cpu()
print(f"CPU usage: {cpu['percent']}%")

error_rate = await health_check.check_error_rate(guild_id=str(ctx.guild.id))
print(f"Error rate: {error_rate['error_rate']}%")

# Get comprehensive health report
health_report = await health_check.get_full_health_report(
    guild_id=str(ctx.guild.id)
)
print(f"Overall status: {health_report['overall_status']}")
print(f"Uptime: {health_report['uptime_seconds']}s")
```

## Helper Functions

For quick, standalone usage without initializing classes:

```python
from utils.monitoring import (
    log_command_execution,
    get_performance_stats,
    get_health_report,
    get_statistics_report
)

# Log command execution
await log_command_execution(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name,
    user_id=str(ctx.author.id),
    username=str(ctx.author),
    command='volume',
    duration=0.234,
    success=True,
    details={'old_volume': 50, 'new_volume': 75}
)

# Get performance statistics
stats = await get_performance_stats(guild_id=str(ctx.guild.id), days=7)

# Get health report
health = await get_health_report(guild_id=str(ctx.guild.id))

# Get statistics report
weekly = await get_statistics_report(guild_id=str(ctx.guild.id), period='weekly')
monthly = await get_statistics_report(guild_id=str(ctx.guild.id), period='monthly')
```

## Complete Integration Example

Here's how to integrate monitoring into a Discord.py cog:

```python
import discord
from discord.ext import commands
from utils.monitoring import create_monitoring_system
from utils.database import Database
import time

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database('data/bot.db')

        # Initialize all monitoring components
        (
            self.cmd_logger,
            self.perf_monitor,
            self.stats_collector,
            self.health_check
        ) = create_monitoring_system(self.db)

    @discord.slash_command(name="play", description="Play a song")
    async def play(self, ctx, song: str):
        start_time = time.perf_counter()
        success = True
        error_msg = None

        try:
            # Track performance
            async with self.perf_monitor.track_command('play', str(ctx.guild.id), str(ctx.author.id)):
                # Your play logic here
                await self.play_song(ctx, song)

                # Record statistics
                await self.stats_collector.record_song_played(
                    guild_id=str(ctx.guild.id),
                    duration=180,  # Get actual duration
                    user_id=str(ctx.author.id)
                )
                await self.stats_collector.record_command(
                    str(ctx.guild.id),
                    str(ctx.author.id)
                )

        except Exception as e:
            success = False
            error_msg = str(e)
            raise

        finally:
            # Log command execution
            duration = time.perf_counter() - start_time
            await self.cmd_logger.log_command(
                guild_id=str(ctx.guild.id),
                guild_name=ctx.guild.name,
                user_id=str(ctx.author.id),
                username=str(ctx.author),
                command='play',
                parameters={'song': song},
                duration=duration,
                success=success,
                error_message=error_msg
            )

    @discord.slash_command(name="stats", description="Show bot statistics")
    async def stats(self, ctx):
        # Get weekly report
        report = await self.stats_collector.generate_weekly_report(
            guild_id=str(ctx.guild.id)
        )

        embed = discord.Embed(
            title="Weekly Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Songs Played", value=report['total_songs'])
        embed.add_field(name="Playtime", value=f"{report['total_playtime_hours']} hours")
        embed.add_field(name="Skip Rate", value=f"{report['skip_rate']}%")
        embed.add_field(name="Active Days", value=report['active_days'])
        embed.add_field(name="Avg Daily Users", value=report['avg_daily_users'])

        await ctx.respond(embed=embed)

    @discord.slash_command(name="health", description="Check bot health")
    async def health(self, ctx):
        # Get health report
        health = await self.health_check.get_full_health_report(
            guild_id=str(ctx.guild.id)
        )

        status_emoji = {
            'healthy': '🟢',
            'degraded': '🟡',
            'unhealthy': '🔴'
        }

        embed = discord.Embed(
            title=f"{status_emoji[health['overall_status']]} Bot Health",
            color=discord.Color.green() if health['overall_status'] == 'healthy' else discord.Color.red()
        )
        embed.add_field(name="Memory", value=f"{health['memory']['rss_mb']} MB")
        embed.add_field(name="CPU", value=f"{health['cpu']['percent']}%")
        embed.add_field(name="Database", value=health['database']['status'])
        embed.add_field(name="Error Rate", value=f"{health['error_rate']['error_rate']}%")
        embed.add_field(name="Uptime", value=f"{health['uptime_seconds']:.0f}s")

        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(MusicCog(bot))
```

## Database Schema Updates

The monitoring module automatically updates your database schema with required columns:

**audit_logs table additions:**
- `username` TEXT
- `guild_name` TEXT
- `parameters` TEXT (JSON)
- `duration` REAL
- `success` INTEGER
- `error_message` TEXT

**bot_stats table additions:**
- `total_pauses` INTEGER
- `unique_users` INTEGER
- `commands_executed` INTEGER

These changes are applied automatically on first run.

## Performance Considerations

1. **Async by Default**: All operations are async and non-blocking
2. **Error Handling**: Safe execution with fallbacks
3. **Caching**: Performance metrics are cached in memory
4. **Database Optimization**: Indexed queries for fast retrieval
5. **Lightweight**: Minimal overhead on command execution

## Best Practices

1. **Initialize Once**: Create monitoring components once at bot startup
2. **Use Context Managers**: Use `track_command()` context manager for automatic timing
3. **Log Consistently**: Log all commands for accurate statistics
4. **Monitor Health**: Check health regularly (every 5-10 minutes)
5. **Generate Reports**: Create reports periodically (daily/weekly)
6. **Clean Old Data**: Use database cleanup methods for old audit logs

## Troubleshooting

### Foreign Key Constraint Errors

Make sure guilds are registered in the `servers` table before logging:

```python
# Register guild first
db.create_server(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name
)
```

### Memory Issues

If memory usage is high, consider:
- Limiting cached metrics
- Cleaning old audit logs regularly
- Using database vacuum periodically

### Slow Performance

Check bottlenecks:
```python
bottlenecks = await perf_monitor.detect_bottlenecks(
    guild_id=str(ctx.guild.id),
    threshold=1.0
)
```

## Testing

Run the test suite:

```bash
python test_monitoring.py
```

## Support

For issues or questions:
1. Check the logs in `bot.log`
2. Review health reports for system issues
3. Check database integrity
4. Verify all dependencies are installed

## Version

Current version: 1.0.0

Last updated: 2025-11-12
