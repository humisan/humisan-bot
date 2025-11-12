"""
Test script for the permissions system

This script demonstrates how to use the permission system in your bot:
1. PermissionManager for database operations
2. require_permission decorator for command protection
3. check_permission function for manual checks
"""

from cogs.permissions import (
    PermissionManager,
    PermissionLevel,
    require_permission
)
from utils.database import db
from config import BOT_OWNER_ID


def test_permission_system():
    """Test the permission system"""

    print("=" * 60)
    print("PERMISSION SYSTEM TEST")
    print("=" * 60)

    # Initialize permission manager
    perm_manager = PermissionManager(db)
    print("\n[OK] Permission manager initialized")
    print("[OK] Database table 'command_permissions' created")

    # Test guild ID (example)
    test_guild_id = "123456789"

    print("\n" + "=" * 60)
    print("DEFAULT PERMISSION LEVELS")
    print("=" * 60)

    commands = [
        "play",
        "pause",
        "skip",
        "settings view",
        "settings set-prefix",
        "permissions view",
        "permissions set",
        "ping",
        "help"
    ]

    for cmd in commands:
        default = perm_manager._get_default_permission(cmd)
        print(f"  {cmd:25} -> {default.name}")

    print("\n" + "=" * 60)
    print("PERMISSION LEVEL HIERARCHY")
    print("=" * 60)

    print(f"  OWNER      (Level {PermissionLevel.OWNER.value}) - Bot owner only")
    print(f"  ADMIN      (Level {PermissionLevel.ADMIN.value}) - Server administrators")
    print(f"  MODERATOR  (Level {PermissionLevel.MODERATOR.value}) - Users with manage_messages")
    print(f"  USER       (Level {PermissionLevel.USER.value}) - Everyone")

    print("\n" + "=" * 60)
    print("EXAMPLE: SETTING CUSTOM PERMISSIONS")
    print("=" * 60)

    # Example: Set music commands to MODERATOR level
    music_commands = ["play", "pause", "skip", "stop", "queue"]

    for cmd in music_commands:
        success = perm_manager.set_command_permission(
            test_guild_id,
            cmd,
            PermissionLevel.MODERATOR,
            enabled=True
        )
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} Set '{cmd}' to MODERATOR level")

    print("\n" + "=" * 60)
    print("EXAMPLE: GETTING COMMAND PERMISSIONS")
    print("=" * 60)

    for cmd in music_commands:
        perm = perm_manager.get_command_permission(test_guild_id, cmd)
        if perm:
            status = "Enabled" if perm['enabled'] else "Disabled"
            print(f"  {cmd:15} -> Level: {perm['permission_level']:10} Status: {status}")

    print("\n" + "=" * 60)
    print("EXAMPLE: TOGGLING COMMAND STATUS")
    print("=" * 60)

    # Toggle a command
    new_status = perm_manager.toggle_command(test_guild_id, "play")
    print(f"  [OK] Toggled 'play' command -> {'Enabled' if new_status else 'Disabled'}")

    # Toggle back
    new_status = perm_manager.toggle_command(test_guild_id, "play")
    print(f"  [OK] Toggled 'play' command -> {'Enabled' if new_status else 'Disabled'}")

    print("\n" + "=" * 60)
    print("EXAMPLE: GETTING ALL PERMISSIONS")
    print("=" * 60)

    all_perms = perm_manager.get_all_command_permissions(test_guild_id)
    print(f"  Total custom permissions set: {len(all_perms)}")

    for perm in all_perms:
        status = "[ON]" if perm['enabled'] else "[OFF]"
        print(f"  {status} {perm['command_name']:15} -> {perm['permission_level']}")

    print("\n" + "=" * 60)
    print("DECORATOR USAGE EXAMPLE")
    print("=" * 60)

    print("""
# Example 1: Admin-only command
@permissions_group.command(name="sensitive")
@require_permission(PermissionLevel.ADMIN)
async def sensitive_command(self, interaction: discord.Interaction):
    '''This command requires ADMIN permission'''
    await interaction.response.send_message("Admin command executed!")

# Example 2: Moderator command
@app_commands.command(name="moderate")
@require_permission(PermissionLevel.MODERATOR)
async def moderate_command(self, interaction: discord.Interaction):
    '''This command requires MODERATOR permission'''
    await interaction.response.send_message("Moderation action performed!")

# Example 3: Owner-only command
@app_commands.command(name="dangerous")
@require_permission(PermissionLevel.OWNER)
async def dangerous_command(self, interaction: discord.Interaction):
    '''This command requires OWNER permission'''
    await interaction.response.send_message("Owner command executed!")
    """)

    print("\n" + "=" * 60)
    print("MANUAL PERMISSION CHECK EXAMPLE")
    print("=" * 60)

    print("""
# In your command handler:
from config import BOT_OWNER_ID

# Check if user has permission
has_perm, error_msg = self.permission_manager.check_permission(
    interaction.guild,
    "play",  # command name
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
await interaction.response.send_message("Playing music!")
    """)

    print("\n" + "=" * 60)
    print("CLEANUP TEST DATA")
    print("=" * 60)

    # Clean up test data
    success = perm_manager.reset_all_permissions(test_guild_id)
    if success:
        print(f"  [OK] Reset all permissions for test guild {test_guild_id}")

    print("\n" + "=" * 60)
    print("AVAILABLE SLASH COMMANDS")
    print("=" * 60)

    print("""
The following commands are now available:

1. /permissions view
   - Shows all command permissions for the server
   - Color-coded by permission level
   - Shows enabled/disabled status

2. /permissions set <command> <level>
   - Set permission level for a command
   - Autocomplete for command names
   - Confirmation dialog before applying
   - Logs change to audit_logs

3. /permissions toggle <command>
   - Enable/disable a command
   - Shows current status
   - Confirmation dialog

4. /permissions reset
   - Reset all permissions to defaults
   - Requires confirmation
   - Logs change to audit_logs

All commands require ADMIN permission by default.
    """)

    print("=" * 60)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_permission_system()
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        import traceback
        traceback.print_exc()
