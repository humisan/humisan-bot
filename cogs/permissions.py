import discord
from discord.ext import commands
from discord import app_commands
from enum import Enum
from typing import Optional, List, Dict, Any
from functools import wraps
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
from utils.database import Database
import sqlite3

logger = setup_logger(__name__)


class PermissionLevel(Enum):
    """Permission levels for bot commands"""
    OWNER = 3
    ADMIN = 2
    USER = 1


class PermissionManager:
    """Manages command permissions and database operations"""

    def __init__(self, db: Database):
        self.db = db
        self._init_permissions_table()
        logger.info("Permission manager initialized")

    def _init_permissions_table(self):
        """Initialize command_permissions table in database"""
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    command_name TEXT NOT NULL,
                    permission_level TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, command_name)
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_command_perms_guild
                ON command_permissions(guild_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_command_perms_command
                ON command_permissions(guild_id, command_name)
            ''')

            conn.commit()
            logger.info("Command permissions table initialized successfully")

        except sqlite3.Error as e:
            logger.error(f"Error initializing permissions table: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_command_permission(self, guild_id: str, command_name: str) -> Optional[Dict[str, Any]]:
        """
        Get permission settings for a specific command

        Args:
            guild_id: Discord guild ID
            command_name: Command name

        Returns:
            Dictionary with permission settings or None
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM command_permissions
                WHERE guild_id = ? AND command_name = ?
            ''', (guild_id, command_name))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error getting command permission: {e}")
            return None
        finally:
            conn.close()

    def get_all_command_permissions(self, guild_id: str) -> List[Dict[str, Any]]:
        """
        Get all command permissions for a guild

        Args:
            guild_id: Discord guild ID

        Returns:
            List of permission dictionaries
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM command_permissions
                WHERE guild_id = ?
                ORDER BY command_name ASC
            ''', (guild_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting all command permissions: {e}")
            return []
        finally:
            conn.close()

    def set_command_permission(self, guild_id: str, command_name: str,
                               permission_level: PermissionLevel, enabled: bool = True) -> bool:
        """
        Set or update command permission

        Args:
            guild_id: Discord guild ID
            command_name: Command name
            permission_level: Required permission level
            enabled: Whether command is enabled

        Returns:
            True if successful, False otherwise
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO command_permissions
                (guild_id, command_name, permission_level, enabled)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, command_name) DO UPDATE SET
                    permission_level = ?,
                    enabled = ?,
                    updated_at = CURRENT_TIMESTAMP
            ''', (guild_id, command_name, permission_level.name, int(enabled),
                  permission_level.name, int(enabled)))

            conn.commit()
            logger.info(f"Permission set for {command_name} in guild {guild_id}: {permission_level.name}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error setting command permission: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def toggle_command(self, guild_id: str, command_name: str) -> Optional[bool]:
        """
        Toggle command enabled status

        Args:
            guild_id: Discord guild ID
            command_name: Command name

        Returns:
            New enabled status (True/False) or None if failed
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            # Get current status
            current = self.get_command_permission(guild_id, command_name)

            if current is None:
                # Create default entry if doesn't exist
                new_status = False
                self.set_command_permission(guild_id, command_name, PermissionLevel.USER, new_status)
                return new_status

            # Toggle status
            new_status = not bool(current['enabled'])

            cursor.execute('''
                UPDATE command_permissions
                SET enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND command_name = ?
            ''', (int(new_status), guild_id, command_name))

            conn.commit()
            logger.info(f"Command {command_name} toggled to {new_status} in guild {guild_id}")
            return new_status

        except sqlite3.Error as e:
            logger.error(f"Error toggling command: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def reset_all_permissions(self, guild_id: str) -> bool:
        """
        Reset all permissions to defaults

        Args:
            guild_id: Discord guild ID

        Returns:
            True if successful, False otherwise
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM command_permissions WHERE guild_id = ?
            ''', (guild_id,))

            conn.commit()
            logger.info(f"All permissions reset in guild {guild_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error resetting permissions: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_user_permission_level(self, guild: discord.Guild, user_id: int, owner_id: int) -> PermissionLevel:
        """
        Get user's permission level

        Args:
            guild: Discord guild
            user_id: User ID
            owner_id: Bot owner ID

        Returns:
            User's permission level
        """
        # Check if user is bot owner
        if user_id == owner_id:
            return PermissionLevel.OWNER

        # Get member
        member = guild.get_member(user_id)
        if member is None:
            return PermissionLevel.USER

        # Check administrator permission
        if member.guild_permissions.administrator:
            return PermissionLevel.ADMIN

        return PermissionLevel.USER

    def check_permission(self, guild: discord.Guild, command_name: str,
                        user_id: int, owner_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if user has permission to use command

        Args:
            guild: Discord guild
            command_name: Command name
            user_id: User ID
            owner_id: Bot owner ID

        Returns:
            Tuple of (has_permission: bool, error_message: Optional[str])
        """
        guild_id = str(guild.id)

        # Get user's permission level
        user_level = self.get_user_permission_level(guild, user_id, owner_id)

        # Get command permission settings
        command_perm = self.get_command_permission(guild_id, command_name)

        # If no specific permission set, use defaults
        if command_perm is None:
            required_level = self._get_default_permission(command_name)
        else:
            # Check if command is enabled
            if not command_perm['enabled']:
                return False, "This command is currently disabled in this server."

            required_level = PermissionLevel[command_perm['permission_level']]

        # Check permission level
        if user_level.value >= required_level.value:
            return True, None

        # Return error message
        error_msg = f"You need **{required_level.name}** permission to use this command. Your permission: **{user_level.name}**"
        return False, error_msg

    def _get_default_permission(self, command_name: str) -> PermissionLevel:
        """
        Get default permission level for a command

        Args:
            command_name: Command name

        Returns:
            Default permission level
        """
        # Settings commands require ADMIN
        if command_name.startswith('settings'):
            return PermissionLevel.ADMIN

        # Permission commands require ADMIN
        if command_name.startswith('permissions'):
            return PermissionLevel.ADMIN

        # All other commands default to USER
        return PermissionLevel.USER


def require_permission(required_level: PermissionLevel):
    """
    Decorator to check command permissions

    Args:
        required_level: Required permission level

    Usage:
        @require_permission(PermissionLevel.ADMIN)
        async def my_command(self, interaction):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # DM check
            if interaction.guild is None:
                await interaction.response.send_message(
                    embed=create_error_embed("This command can only be used in a server"),
                    ephemeral=True
                )
                return

            # Get permission manager
            if not hasattr(self, 'permission_manager'):
                logger.error("Cog does not have permission_manager attribute")
                await interaction.response.send_message(
                    embed=create_error_embed("Permission system not initialized"),
                    ephemeral=True
                )
                return

            # Get bot owner ID from config
            from config import BOT_OWNER_ID

            # Check permission
            has_perm, error_msg = self.permission_manager.check_permission(
                interaction.guild,
                func.__name__,
                interaction.user.id,
                BOT_OWNER_ID
            )

            if not has_perm:
                await interaction.response.send_message(
                    embed=create_error_embed("Insufficient Permissions", error_msg),
                    ephemeral=True
                )
                return

            # Execute command
            return await func(self, interaction, *args, **kwargs)

        return wrapper
    return decorator


class ConfirmView(discord.ui.View):
    """Confirmation view for permission changes"""

    def __init__(self, user_id: int):
        super().__init__(timeout=30.0)
        self.user_id = user_id
        self.value = None

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm button callback"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=create_error_embed("You are not authorized to confirm this action"),
                ephemeral=True
            )
            return

        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel button callback"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=create_error_embed("You are not authorized to cancel this action"),
                ephemeral=True
            )
            return

        self.value = False
        self.stop()
        await interaction.response.defer()


class Permissions(commands.Cog):
    """Permission management for bot commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize database connection
        from utils.database import db
        self.db = db
        self.permission_manager = PermissionManager(db)
        logger.info("Permissions Cog loaded")

    def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has administrator permissions"""
        if interaction.guild is None:
            return False

        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            return False

        return member.guild_permissions.administrator

    def _get_all_bot_commands(self) -> List[str]:
        """Get all bot command names"""
        commands = []

        # Get all app commands
        for command in self.bot.tree.get_commands():
            if isinstance(command, app_commands.Group):
                # Handle command groups
                for subcommand in command.commands:
                    commands.append(f"{command.name} {subcommand.name}")
            else:
                commands.append(command.name)

        return sorted(commands)

    def _get_permission_color(self, level: str) -> discord.Color:
        """Get color for permission level"""
        colors = {
            'OWNER': discord.Color.purple(),
            'ADMIN': discord.Color.red(),
            'USER': discord.Color.green()
        }
        return colors.get(level, discord.Color.blue())

    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for command names"""
        commands = self._get_all_bot_commands()
        return [
            app_commands.Choice(name=cmd, value=cmd)
            for cmd in commands
            if current.lower() in cmd.lower()
        ][:25]  # Discord limits to 25 choices

    permissions_group = app_commands.Group(
        name="permissions",
        description="Manage command permissions"
    )

    @permissions_group.command(name="view", description="View all command permissions")
    async def permissions_view(self, interaction: discord.Interaction):
        """Display all command permissions for this server"""
        # DM check
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        # Admin check
        if not self._check_admin(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("You need administrator permissions to view permissions"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)

            # Get all permissions
            permissions = self.permission_manager.get_all_command_permissions(guild_id)

            # Get all bot commands
            all_commands = self._get_all_bot_commands()

            # Create embed
            embed = discord.Embed(
                title=f"Command Permissions - {interaction.guild.name}",
                description="Command permission levels and status",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            # Build permission map
            perm_map = {p['command_name']: p for p in permissions}

            # Group commands by permission level
            grouped: Dict[str, List[str]] = {
                'OWNER': [],
                'ADMIN': [],
                'USER': []
            }

            for cmd in all_commands:
                if cmd in perm_map:
                    perm = perm_map[cmd]
                    level = perm['permission_level']
                    status = "✅" if perm['enabled'] else "❌"
                    grouped[level].append(f"{status} `{cmd}`")
                else:
                    # Use default
                    default_level = self.permission_manager._get_default_permission(cmd)
                    grouped[default_level.name].append(f"✅ `{cmd}` (default)")

            # Add fields for each permission level
            for level in ['OWNER', 'ADMIN', 'USER']:
                if grouped[level]:
                    commands_text = '\n'.join(grouped[level][:10])
                    if len(grouped[level]) > 10:
                        commands_text += f"\n*...and {len(grouped[level]) - 10} more*"

                    embed.add_field(
                        name=f"{level} Level ({len(grouped[level])} commands)",
                        value=commands_text or "No commands",
                        inline=False
                    )

            embed.set_footer(text="✅ = Enabled | ❌ = Disabled | (default) = Using default settings")

            await interaction.response.send_message(embed=embed)

            # Log command
            self.db.log_command(guild_id, str(interaction.user.id), "permissions view")

        except Exception as e:
            logger.error(f"Error in permissions view command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to display permissions", str(e)),
                ephemeral=True
            )

    @permissions_group.command(name="set", description="Set command permission level")
    @app_commands.describe(
        command="Command name",
        level="Required permission level"
    )
    @app_commands.autocomplete(command=command_autocomplete)
    @app_commands.choices(level=[
        app_commands.Choice(name="OWNER - Bot owner only", value="OWNER"),
        app_commands.Choice(name="ADMIN - Server administrators", value="ADMIN"),
        app_commands.Choice(name="USER - Everyone", value="USER")
    ])
    async def permissions_set(
        self,
        interaction: discord.Interaction,
        command: str,
        level: str
    ):
        """Set permission level for a command"""
        # DM check
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        # Admin check
        if not self._check_admin(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("You need administrator permissions to change permissions"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            permission_level = PermissionLevel[level]

            # Create confirmation embed
            current = self.permission_manager.get_command_permission(guild_id, command)
            if current:
                current_level = current['permission_level']
                current_status = "Enabled" if current['enabled'] else "Disabled"
            else:
                default = self.permission_manager._get_default_permission(command)
                current_level = default.name
                current_status = "Enabled (default)"

            confirm_embed = discord.Embed(
                title="Confirm Permission Change",
                description=f"Are you sure you want to change the permission level for `{command}`?",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            confirm_embed.add_field(
                name="Current Level",
                value=f"{current_level} ({current_status})",
                inline=True
            )

            confirm_embed.add_field(
                name="New Level",
                value=level,
                inline=True
            )

            confirm_embed.add_field(
                name="Effect",
                value=self._get_level_description(permission_level),
                inline=False
            )

            view = ConfirmView(interaction.user.id)
            await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

            # Wait for confirmation
            await view.wait()

            if view.value is None:
                await interaction.edit_original_response(
                    embed=create_error_embed("Confirmation timeout", "Permission change cancelled"),
                    view=None
                )
                return

            if not view.value:
                await interaction.edit_original_response(
                    embed=create_success_embed("Cancelled", "Permission change cancelled"),
                    view=None
                )
                return

            # Apply permission change
            success = self.permission_manager.set_command_permission(
                guild_id,
                command,
                permission_level,
                enabled=True
            )

            if success:
                success_embed = create_success_embed(
                    "Permission Updated",
                    f"Command `{command}` now requires **{level}** permission"
                )
                success_embed.set_footer(text=f"Changed by {interaction.user}")

                await interaction.edit_original_response(embed=success_embed, view=None)

                # Log command
                self.db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "permissions set",
                    f"Command: {command}, Level: {level}"
                )

                logger.info(f"Permission set for {command} to {level} in guild {guild_id}")
            else:
                await interaction.edit_original_response(
                    embed=create_error_embed("Failed to update permission"),
                    view=None
                )

        except Exception as e:
            logger.error(f"Error in permissions set command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to set permission", str(e)),
                ephemeral=True
            )

    def _get_level_description(self, level: PermissionLevel) -> str:
        """Get description for permission level"""
        descriptions = {
            PermissionLevel.OWNER: "Only the bot owner can use this command",
            PermissionLevel.ADMIN: "Only server administrators can use this command",
            PermissionLevel.USER: "Everyone can use this command"
        }
        return descriptions.get(level, "Unknown permission level")

    @permissions_group.command(name="toggle", description="Enable/disable a command")
    @app_commands.describe(command="Command name to toggle")
    @app_commands.autocomplete(command=command_autocomplete)
    async def permissions_toggle(self, interaction: discord.Interaction, command: str):
        """Toggle command enabled status"""
        # DM check
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        # Admin check
        if not self._check_admin(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("You need administrator permissions to toggle commands"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)

            # Get current status
            current = self.permission_manager.get_command_permission(guild_id, command)
            if current:
                current_status = bool(current['enabled'])
            else:
                current_status = True  # Default is enabled

            # Create confirmation embed
            new_status = not current_status
            action = "disable" if current_status else "enable"

            confirm_embed = discord.Embed(
                title=f"Confirm Command {action.title()}",
                description=f"Are you sure you want to **{action}** the `{command}` command?",
                color=discord.Color.orange() if action == "disable" else discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            confirm_embed.add_field(
                name="Current Status",
                value="✅ Enabled" if current_status else "❌ Disabled",
                inline=True
            )

            confirm_embed.add_field(
                name="New Status",
                value="✅ Enabled" if new_status else "❌ Disabled",
                inline=True
            )

            if not new_status:
                confirm_embed.add_field(
                    name="Warning",
                    value="Users will not be able to use this command when disabled",
                    inline=False
                )

            view = ConfirmView(interaction.user.id)
            await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

            # Wait for confirmation
            await view.wait()

            if view.value is None:
                await interaction.edit_original_response(
                    embed=create_error_embed("Confirmation timeout", "Command toggle cancelled"),
                    view=None
                )
                return

            if not view.value:
                await interaction.edit_original_response(
                    embed=create_success_embed("Cancelled", "Command toggle cancelled"),
                    view=None
                )
                return

            # Toggle command
            new_status = self.permission_manager.toggle_command(guild_id, command)

            if new_status is not None:
                status_text = "enabled" if new_status else "disabled"
                status_emoji = "✅" if new_status else "❌"

                success_embed = create_success_embed(
                    f"Command {status_text.title()}",
                    f"{status_emoji} Command `{command}` has been **{status_text}**"
                )
                success_embed.set_footer(text=f"Changed by {interaction.user}")

                await interaction.edit_original_response(embed=success_embed, view=None)

                # Log command
                self.db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "permissions toggle",
                    f"Command: {command}, Status: {status_text}"
                )

                logger.info(f"Command {command} {status_text} in guild {guild_id}")
            else:
                await interaction.edit_original_response(
                    embed=create_error_embed("Failed to toggle command"),
                    view=None
                )

        except Exception as e:
            logger.error(f"Error in permissions toggle command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to toggle command", str(e)),
                ephemeral=True
            )

    @permissions_group.command(name="reset", description="Reset all permissions to defaults")
    async def permissions_reset(self, interaction: discord.Interaction):
        """Reset all permissions to defaults"""
        # DM check
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        # Admin check
        if not self._check_admin(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("You need administrator permissions to reset permissions"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)

            # Create confirmation embed
            confirm_embed = discord.Embed(
                title="Confirm Permission Reset",
                description="Are you sure you want to reset **all** command permissions to defaults?",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )

            confirm_embed.add_field(
                name="This will reset:",
                value=(
                    "• All custom permission levels\n"
                    "• All enabled/disabled states\n"
                    "• Commands will use default permissions:\n"
                    "  - Music commands: **USER** level\n"
                    "  - Settings commands: **ADMIN** level\n"
                    "  - Utility commands: **USER** level"
                ),
                inline=False
            )

            confirm_embed.add_field(
                name="Warning",
                value="This action cannot be undone!",
                inline=False
            )

            view = ConfirmView(interaction.user.id)
            await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

            # Wait for confirmation
            await view.wait()

            if view.value is None:
                await interaction.edit_original_response(
                    embed=create_error_embed("Confirmation timeout", "Permission reset cancelled"),
                    view=None
                )
                return

            if not view.value:
                await interaction.edit_original_response(
                    embed=create_success_embed("Cancelled", "Permission reset cancelled"),
                    view=None
                )
                return

            # Reset permissions
            success = self.permission_manager.reset_all_permissions(guild_id)

            if success:
                success_embed = create_success_embed(
                    "Permissions Reset",
                    "All command permissions have been reset to defaults"
                )
                success_embed.add_field(
                    name="Default Settings Applied",
                    value=(
                        "• Music commands: USER level\n"
                        "• Settings commands: ADMIN level\n"
                        "• Utility commands: USER level\n"
                        "• All commands: Enabled"
                    ),
                    inline=False
                )
                success_embed.set_footer(text=f"Reset by {interaction.user}")

                await interaction.edit_original_response(embed=success_embed, view=None)

                # Log command
                self.db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "permissions reset",
                    "All permissions reset to defaults"
                )

                logger.info(f"All permissions reset in guild {guild_id}")
            else:
                await interaction.edit_original_response(
                    embed=create_error_embed("Failed to reset permissions"),
                    view=None
                )

        except Exception as e:
            logger.error(f"Error in permissions reset command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to reset permissions", str(e)),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Setup function to load the cog"""
    await bot.add_cog(Permissions(bot))
