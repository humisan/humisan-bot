# Permission Management System - Complete Guide

## Overview

The Permission Management System provides fine-grained control over bot commands at the server level. It allows server administrators to set permission levels for each command and enable/disable commands as needed.

## Features

- **4 Permission Levels**: OWNER, ADMIN, MODERATOR, USER
- **Command-Level Control**: Set permissions for individual commands
- **Enable/Disable Commands**: Toggle command availability per server
- **Audit Logging**: All permission changes are logged
- **Default Permissions**: Smart defaults based on command type
- **Easy Integration**: Simple decorator pattern for command protection

---

## Permission Levels

### Level Hierarchy

```
OWNER (Level 4)      - Bot owner only (from BOT_OWNER_ID in config)
  |
ADMIN (Level 3)      - Server administrators (has administrator permission)
  |
MODERATOR (Level 2)  - Users with manage_messages permission
  |
USER (Level 1)       - Everyone
```

### Permission Descriptions

1. **OWNER** (Level 4)
   - Only the bot owner can use these commands
   - Set via `BOT_OWNER_ID` in your `.env` file
   - Use for dangerous/maintenance commands

2. **ADMIN** (Level 3)
   - Server administrators only
   - Requires Discord `administrator` permission
   - Default for settings and permission commands

3. **MODERATOR** (Level 2)
   - Users with `manage_messages` permission
   - Good for moderation commands

4. **USER** (Level 1)
   - Everyone can use these commands
   - Default for music and utility commands

---

## Slash Commands

All permission commands are under the `/permissions` group and require ADMIN permission by default.

### 1. `/permissions view`

Shows all command permissions for the server.

**Features:**
- Lists all bot commands
- Groups by permission level
- Shows enabled/disabled status
- Color-coded embeds

**Example Output:**
```
OWNER Level (2 commands)
[ON] backup
[ON] shutdown

ADMIN Level (8 commands)
[ON] settings view
[ON] settings set-prefix
[ON] permissions view
...

MODERATOR Level (5 commands)
[ON] kick
[ON] ban
[OFF] mute (disabled)
...

USER Level (15 commands)
[ON] play (default)
[ON] pause (default)
...
```

### 2. `/permissions set <command> <level>`

Set permission level for a specific command.

**Parameters:**
- `command`: Command name (autocomplete enabled)
- `level`: OWNER, ADMIN, MODERATOR, or USER

**Features:**
- Autocomplete for command names
- Confirmation dialog before applying
- Shows current vs. new permission
- Logs change to audit_logs

**Example:**
```
/permissions set command:play level:MODERATOR
```

This requires moderator permission to use the play command.

### 3. `/permissions toggle <command>`

Enable or disable a command.

**Parameters:**
- `command`: Command name (autocomplete enabled)

**Features:**
- Toggle command availability
- Confirmation dialog
- Shows current status
- Logs change to audit_logs

**Example:**
```
/permissions toggle command:skip
```

### 4. `/permissions reset`

Reset all permissions to defaults.

**Features:**
- Resets all custom permissions
- Requires confirmation
- Shows what will be reset
- Logs to audit_logs

**Defaults after reset:**
- Music commands: USER level
- Settings commands: ADMIN level
- Utility commands: USER level
- All commands: Enabled

---

## Using the Permission System in Your Code

### Method 1: Using the Decorator (Recommended)

The easiest way to protect commands is using the `@require_permission` decorator:

```python
from cogs.permissions import require_permission, PermissionLevel
from discord import app_commands
import discord

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize permission manager
        from utils.database import db
        from cogs.permissions import PermissionManager
        self.permission_manager = PermissionManager(db)

    @app_commands.command(name="dangerous")
    @require_permission(PermissionLevel.OWNER)
    async def dangerous_command(self, interaction: discord.Interaction):
        """Only bot owner can use this"""
        await interaction.response.send_message("Owner command executed!")

    @app_commands.command(name="admin")
    @require_permission(PermissionLevel.ADMIN)
    async def admin_command(self, interaction: discord.Interaction):
        """Only admins can use this"""
        await interaction.response.send_message("Admin command executed!")

    @app_commands.command(name="moderate")
    @require_permission(PermissionLevel.MODERATOR)
    async def moderate_command(self, interaction: discord.Interaction):
        """Moderators and above can use this"""
        await interaction.response.send_message("Moderation action performed!")
```

**Important Notes:**
- Your Cog must have a `permission_manager` attribute
- The decorator automatically handles DM checks
- Returns proper error messages
- Respects custom permissions set by server admins

### Method 2: Manual Permission Check

For more control, check permissions manually:

```python
from cogs.permissions import PermissionManager
from config import BOT_OWNER_ID
from utils.helpers import create_error_embed

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from utils.database import db
        self.permission_manager = PermissionManager(db)

    @app_commands.command(name="mycommand")
    async def my_command(self, interaction: discord.Interaction):
        # Check if in guild
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        # Check permission
        has_perm, error_msg = self.permission_manager.check_permission(
            interaction.guild,
            "mycommand",  # command name
            interaction.user.id,
            BOT_OWNER_ID
        )

        if not has_perm:
            await interaction.response.send_message(
                embed=create_error_embed("Insufficient Permissions", error_msg),
                ephemeral=True
            )
            return

        # User has permission, execute command
        await interaction.response.send_message("Command executed!")
```

---

## Database Schema

### Table: `command_permissions`

```sql
CREATE TABLE command_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    command_name TEXT NOT NULL,
    permission_level TEXT NOT NULL,  -- OWNER, ADMIN, MODERATOR, USER
    enabled INTEGER DEFAULT 1,        -- 1 = enabled, 0 = disabled
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, command_name)
);
```

### Indexes

```sql
CREATE INDEX idx_command_perms_guild ON command_permissions(guild_id);
CREATE INDEX idx_command_perms_command ON command_permissions(guild_id, command_name);
```

---

## Permission Manager API

### Initialize Permission Manager

```python
from utils.database import db
from cogs.permissions import PermissionManager

perm_manager = PermissionManager(db)
```

### Get User Permission Level

```python
level = perm_manager.get_user_permission_level(
    guild=interaction.guild,
    user_id=interaction.user.id,
    owner_id=BOT_OWNER_ID
)
# Returns: PermissionLevel.OWNER, ADMIN, MODERATOR, or USER
```

### Check Permission

```python
has_permission, error_message = perm_manager.check_permission(
    guild=interaction.guild,
    command_name="play",
    user_id=interaction.user.id,
    owner_id=BOT_OWNER_ID
)

if not has_permission:
    print(error_message)  # "You need ADMIN permission..."
```

### Get Command Permission

```python
perm = perm_manager.get_command_permission(
    guild_id=str(guild.id),
    command_name="play"
)

if perm:
    print(f"Level: {perm['permission_level']}")
    print(f"Enabled: {perm['enabled']}")
else:
    print("Using default permission")
```

### Get All Permissions

```python
permissions = perm_manager.get_all_command_permissions(
    guild_id=str(guild.id)
)

for perm in permissions:
    print(f"{perm['command_name']}: {perm['permission_level']}")
```

### Set Command Permission

```python
success = perm_manager.set_command_permission(
    guild_id=str(guild.id),
    command_name="play",
    permission_level=PermissionLevel.MODERATOR,
    enabled=True
)
```

### Toggle Command

```python
new_status = perm_manager.toggle_command(
    guild_id=str(guild.id),
    command_name="play"
)

print(f"Command is now: {'Enabled' if new_status else 'Disabled'}")
```

### Reset All Permissions

```python
success = perm_manager.reset_all_permissions(
    guild_id=str(guild.id)
)
```

---

## Default Permission Rules

The system uses smart defaults based on command names:

### Admin Level (Default)
- Commands starting with `settings`
- Commands starting with `permissions`

### User Level (Default)
- All other commands (music, utility, etc.)

### Examples:

| Command | Default Level | Reason |
|---------|---------------|--------|
| `play` | USER | Music command |
| `pause` | USER | Music command |
| `settings view` | ADMIN | Settings command |
| `settings set-prefix` | ADMIN | Settings command |
| `permissions view` | ADMIN | Permission command |
| `permissions set` | ADMIN | Permission command |
| `ping` | USER | Utility command |
| `help` | USER | Utility command |

---

## Best Practices

### 1. Use Appropriate Permission Levels

```python
# ❌ Bad - Music command requires ADMIN
@require_permission(PermissionLevel.ADMIN)
async def play(self, interaction):
    ...

# ✅ Good - Music command uses default (USER)
async def play(self, interaction):
    ...

# ✅ Good - Dangerous command requires OWNER
@require_permission(PermissionLevel.OWNER)
async def shutdown(self, interaction):
    ...
```

### 2. Always Check for Guild Context

```python
# ✅ Good - Decorator handles this automatically
@require_permission(PermissionLevel.ADMIN)
async def my_command(self, interaction):
    ...

# ✅ Good - Manual check
async def my_command(self, interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Guild only!", ephemeral=True)
        return
```

### 3. Log Important Permission Changes

```python
# ✅ Good - Log to audit_logs
self.db.log_command(
    guild_id,
    str(interaction.user.id),
    "permissions set",
    f"Command: {command}, Level: {level}"
)
```

### 4. Provide Clear Error Messages

```python
# ❌ Bad
await interaction.response.send_message("No permission")

# ✅ Good
await interaction.response.send_message(
    embed=create_error_embed(
        "Insufficient Permissions",
        "You need **ADMIN** permission to use this command. Your permission: **USER**"
    ),
    ephemeral=True
)
```

---

## Example: Protecting an Existing Cog

Let's protect the Music cog with permissions:

```python
import discord
from discord.ext import commands
from discord import app_commands
from cogs.permissions import PermissionManager, require_permission, PermissionLevel
from utils.database import db

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(db)  # Add this!

    # Option 1: Use decorator for group commands
    music_group = app_commands.Group(name="music", description="Music commands")

    @music_group.command(name="play")
    # No decorator needed - uses default USER level
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song"""
        await interaction.response.send_message(f"Playing: {query}")

    @music_group.command(name="clear")
    @require_permission(PermissionLevel.MODERATOR)  # Moderator+ only
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        await interaction.response.send_message("Queue cleared!")

    # Option 2: Manual check for more control
    @music_group.command(name="volume")
    async def volume(self, interaction: discord.Interaction, level: int):
        """Set volume"""
        if interaction.guild is None:
            return

        # Check permission manually
        from config import BOT_OWNER_ID
        has_perm, error_msg = self.permission_manager.check_permission(
            interaction.guild,
            "volume",
            interaction.user.id,
            BOT_OWNER_ID
        )

        if not has_perm:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        # Execute command
        await interaction.response.send_message(f"Volume set to {level}")

async def setup(bot):
    await bot.add_cog(Music(bot))
```

---

## Troubleshooting

### Permission Decorator Not Working

**Problem:** `AttributeError: 'MyCog' object has no attribute 'permission_manager'`

**Solution:** Initialize `permission_manager` in your Cog's `__init__`:

```python
def __init__(self, bot):
    self.bot = bot
    from utils.database import db
    from cogs.permissions import PermissionManager
    self.permission_manager = PermissionManager(db)
```

### Command Not Showing in `/permissions view`

**Problem:** Command doesn't appear in permission list

**Reasons:**
1. Command not synced to Discord yet
2. Command is in a guild-specific tree (only global commands shown)

**Solution:** Sync your commands:
```python
await bot.tree.sync()
```

### Users Can't Use Commands After Setting Permissions

**Problem:** Users get "Insufficient Permissions" even though they should have access

**Check:**
1. Is the command enabled? (`/permissions toggle`)
2. Does user have the required Discord permission?
3. Is permission level set correctly?

**Debug:**
```python
# Check user's permission level
level = perm_manager.get_user_permission_level(guild, user_id, owner_id)
print(f"User level: {level}")

# Check command permission
perm = perm_manager.get_command_permission(guild_id, command_name)
print(f"Command level: {perm['permission_level'] if perm else 'default'}")
```

---

## Migration from Old System

If you're upgrading from a system without permissions:

### Step 1: Install the Cog

The cog is already installed at: `C:\Users\humis\PycharmProjects\PythonProject\cogs\permissions.py`

### Step 2: Add to Existing Cogs

Add permission manager to your existing cogs:

```python
# In each cog's __init__
from utils.database import db
from cogs.permissions import PermissionManager

self.permission_manager = PermissionManager(db)
```

### Step 3: Protect Commands

Add decorators to commands that need protection:

```python
from cogs.permissions import require_permission, PermissionLevel

@require_permission(PermissionLevel.ADMIN)
async def sensitive_command(self, interaction):
    ...
```

### Step 4: Update Bot Owner ID

Make sure `BOT_OWNER_ID` is set in your `.env` file:

```
BOT_OWNER_ID=123456789012345678
```

---

## Summary

### Files Created
- `C:\Users\humis\PycharmProjects\PythonProject\cogs\permissions.py` - Main Cog
- `C:\Users\humis\PycharmProjects\PythonProject\test_permissions.py` - Test/Demo script
- `C:\Users\humis\PycharmProjects\PythonProject\PERMISSIONS_GUIDE.md` - This guide

### Key Components
1. **PermissionLevel Enum** - 4 permission levels
2. **PermissionManager Class** - Database operations
3. **@require_permission Decorator** - Easy command protection
4. **Slash Commands** - `/permissions view`, `set`, `toggle`, `reset`
5. **Database Table** - `command_permissions`

### Quick Start
1. Cog is automatically loaded by bot
2. Use `/permissions view` to see current permissions
3. Use `/permissions set` to change permissions
4. Add `@require_permission()` decorator to protect commands

---

## Support

For issues or questions:
1. Check this guide first
2. Run `python test_permissions.py` to verify system
3. Check logs in `bot.log`
4. Review audit_logs table for permission changes

---

**Permission Management System v1.0**
*Created for Discord Music Bot*
