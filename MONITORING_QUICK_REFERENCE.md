# Monitoring Module - Quick Reference

## Quick Start

```python
from utils.monitoring import create_monitoring_system
from utils.database import Database

# Initialize all monitoring components at once
db = Database('data/bot.db')
cmd_logger, perf_monitor, stats_collector, health_check = create_monitoring_system(db)
```

## Common Operations

### 1. Log a Command

```python
await cmd_logger.log_command(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name,
    user_id=str(ctx.author.id),
    username=str(ctx.author),
    command='play',
    parameters={'song': song_name},
    duration=0.456,
    success=True
)
```

### 2. Track Performance

```python
async with perf_monitor.track_command('play', str(ctx.guild.id), str(ctx.author.id)):
    await your_command_logic()
```

### 3. Record Statistics

```python
# Record song played
await stats_collector.record_song_played(str(ctx.guild.id), duration=180, user_id=str(ctx.author.id))

# Record skip
await stats_collector.record_skip(str(ctx.guild.id))

# Record pause
await stats_collector.record_pause(str(ctx.guild.id))

# Record command
await stats_collector.record_command(str(ctx.guild.id), str(ctx.author.id))
```

### 4. Get Reports

```python
# Weekly report
weekly = await stats_collector.generate_weekly_report(str(ctx.guild.id))

# Monthly report
monthly = await stats_collector.generate_monthly_report(str(ctx.guild.id))

# Daily stats
daily = await stats_collector.get_daily_stats(str(ctx.guild.id))
```

### 5. Health Check

```python
# Full health report
health = await health_check.get_full_health_report(str(ctx.guild.id))
print(f"Status: {health['overall_status']}")

# Individual checks
memory = await health_check.check_memory()
database = await health_check.check_database()
cpu = await health_check.check_cpu()
errors = await health_check.check_error_rate(str(ctx.guild.id))
```

## Helper Functions (No Class Initialization)

```python
from utils.monitoring import (
    log_command_execution,
    get_performance_stats,
    get_health_report,
    get_statistics_report
)

# Quick command logging
await log_command_execution(
    guild_id=str(ctx.guild.id),
    guild_name=ctx.guild.name,
    user_id=str(ctx.author.id),
    username=str(ctx.author),
    command='volume',
    duration=0.234,
    success=True,
    details={'volume': 75}
)

# Quick stats
stats = await get_performance_stats(str(ctx.guild.id), days=7)

# Quick health check
health = await get_health_report(str(ctx.guild.id))

# Quick reports
weekly = await get_statistics_report(str(ctx.guild.id), period='weekly')
monthly = await get_statistics_report(str(ctx.guild.id), period='monthly')
```

## Integration Pattern

```python
import time

@discord.slash_command(name="play")
async def play(self, ctx, song: str):
    start_time = time.perf_counter()
    success = True
    error_msg = None

    try:
        async with self.perf_monitor.track_command('play', str(ctx.guild.id), str(ctx.author.id)):
            # Your command logic
            result = await self.play_song(ctx, song)

            # Record stats
            await self.stats_collector.record_song_played(
                str(ctx.guild.id),
                result['duration'],
                str(ctx.author.id)
            )
    except Exception as e:
        success = False
        error_msg = str(e)
        raise
    finally:
        # Always log
        await self.cmd_logger.log_command(
            guild_id=str(ctx.guild.id),
            guild_name=ctx.guild.name,
            user_id=str(ctx.author.id),
            username=str(ctx.author),
            command='play',
            parameters={'song': song},
            duration=time.perf_counter() - start_time,
            success=success,
            error_message=error_msg
        )
```

## Available Data Fields

### Command Log Entry
```python
{
    'id': int,
    'guild_id': str,
    'guild_name': str,
    'user_id': str,
    'username': str,
    'command': str,
    'parameters': dict,  # JSON
    'duration': float,
    'success': bool,
    'error_message': str,
    'executed_at': datetime
}
```

### Performance Stats
```python
{
    'slowest_commands': [{
        'command': str,
        'avg_duration': float,
        'min_duration': float,
        'max_duration': float,
        'count': int
    }],
    'cache_metrics': {...}
}
```

### Weekly/Monthly Report
```python
{
    'period': str,
    'days': int,
    'active_days': int,
    'total_songs': int,
    'total_playtime': int,
    'total_playtime_hours': float,
    'total_skips': int,
    'total_pauses': int,
    'total_commands': int,
    'avg_daily_users': float,
    'peak_users': int,
    'avg_song_duration': float,
    'skip_rate': float,
    'top_commands': [...]
}
```

### Health Report
```python
{
    'timestamp': str,
    'overall_status': str,  # 'healthy', 'degraded', 'unhealthy'
    'memory': {
        'rss_mb': float,
        'vms_mb': float,
        'percent': float,
        'status': str
    },
    'database': {
        'connected': bool,
        'response_time': float,
        'server_count': int,
        'database_size_mb': float,
        'status': str
    },
    'cpu': {
        'percent': float,
        'user_time': float,
        'system_time': float,
        'status': str
    },
    'error_rate': {
        'total_commands': int,
        'failed_commands': int,
        'error_rate': float,
        'status': str
    },
    'uptime_seconds': float
}
```

## Performance Thresholds

The module uses these default thresholds:

```python
thresholds = {
    'command_slow': 2.0,      # seconds - commands slower trigger warning
    'voice_connect_slow': 5.0, # seconds - voice connection slow warning
    'response_slow': 1.0       # seconds - response latency warning
}
```

## Status Values

- **Overall Status**: `healthy`, `degraded`, `unhealthy`
- **Component Status**: `healthy`, `warning`, `critical`, `slow`, `error`
- **Bottleneck Severity**: `high`, `medium`

## Database Tables Used

1. **audit_logs** - Command execution logs
2. **bot_stats** - Daily statistics
3. **servers** - Guild information (required for foreign keys)

## Error Handling

All methods use the `@safe_execute` decorator:
- Returns default value on error (empty dict, list, False, etc.)
- Logs errors automatically
- Never crashes your bot

## Memory Management

- Performance metrics cache: Limited to 1000 entries per metric type
- Health history: Limited to 100 most recent checks
- Audit logs: Use `clear_old_audit_logs(days=30)` to clean up

## Testing

```bash
python test_monitoring.py
```

## Dependencies

- `psutil>=5.9.0` - System monitoring (install: `pip install psutil`)
- `sqlite3` - Database (built-in)
- `asyncio` - Async support (built-in)

## Tips

1. **Always register guilds** before logging commands
2. **Use context managers** for automatic performance tracking
3. **Check health regularly** (every 5-10 minutes)
4. **Generate reports asynchronously** to avoid blocking
5. **Clean old logs** periodically to manage database size

---

For detailed documentation, see `MONITORING_USAGE_GUIDE.md`
