# Permission System - Quick Reference

## Slash Commands (Admin Only)

```
/permissions view                           - View all permissions
/permissions set <command> <level>          - Set permission level
/permissions toggle <command>               - Enable/disable command
/permissions reset                          - Reset to defaults
```

## Permission Levels

```
OWNER (4)      - Bot owner only
ADMIN (3)      - Server administrators
MODERATOR (2)  - Users with manage_messages
USER (1)       - Everyone
```

## Decorator Usage

```python
from cogs.permissions import require_permission, PermissionLevel

# Add to your Cog's __init__:
def __init__(self, bot):
    self.bot = bot
    from utils.database import db
    from cogs.permissions import PermissionManager
    self.permission_manager = PermissionManager(db)

# Protect commands:
@app_commands.command(name="admin")
@require_permission(PermissionLevel.ADMIN)
async def admin_command(self, interaction):
    await interaction.response.send_message("Admin only!")

@app_commands.command(name="mod")
@require_permission(PermissionLevel.MODERATOR)
async def mod_command(self, interaction):
    await interaction.response.send_message("Moderator+!")

@app_commands.command(name="owner")
@require_permission(PermissionLevel.OWNER)
async def owner_command(self, interaction):
    await interaction.response.send_message("Owner only!")
```

## Manual Check

```python
from config import BOT_OWNER_ID

has_perm, error_msg = self.permission_manager.check_permission(
    interaction.guild,
    "command_name",
    interaction.user.id,
    BOT_OWNER_ID
)

if not has_perm:
    await interaction.response.send_message(error_msg, ephemeral=True)
    return
```

## API Methods

```python
from utils.database import db
from cogs.permissions import PermissionManager, PermissionLevel

pm = PermissionManager(db)

# Get user's permission level
level = pm.get_user_permission_level(guild, user_id, owner_id)

# Check permission
has_perm, msg = pm.check_permission(guild, "play", user_id, owner_id)

# Get command permission
perm = pm.get_command_permission(guild_id, "play")

# Get all permissions
all_perms = pm.get_all_command_permissions(guild_id)

# Set permission
pm.set_command_permission(guild_id, "play", PermissionLevel.MODERATOR, True)

# Toggle command
new_status = pm.toggle_command(guild_id, "play")

# Reset all
pm.reset_all_permissions(guild_id)
```

## Default Permissions

| Command Type | Default Level |
|-------------|---------------|
| settings *  | ADMIN         |
| permissions *| ADMIN        |
| All others  | USER          |

## Database Table

```sql
command_permissions (
    id, guild_id, command_name,
    permission_level, enabled,
    created_at, updated_at
)
```

## Files

- `cogs/permissions.py` - Main Cog
- `test_permissions.py` - Test script
- `PERMISSIONS_GUIDE.md` - Full documentation

## Test

```bash
python test_permissions.py
```
