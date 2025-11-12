import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
from utils.database import db

logger = setup_logger(__name__)


class ConfirmView(discord.ui.View):
    """Confirmation view for destructive operations"""

    def __init__(self, user_id: int):
        super().__init__(timeout=30.0)
        self.user_id = user_id
        self.value = None

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.danger)
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


class Settings(commands.Cog):
    """Server settings management"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has administrator permissions"""
        if interaction.guild is None:
            return False

        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            return False

        return member.guild_permissions.administrator

    async def _ensure_server_exists(self, guild_id: str, guild_name: str) -> bool:
        """Ensure server entry exists in database"""
        settings = db.get_server_settings(guild_id)
        if settings is None:
            return db.create_server(guild_id, guild_name)
        return True

    settings_group = app_commands.Group(name="settings", description="Server settings management")

    @settings_group.command(name="view", description="Display current server settings")
    async def settings_view(self, interaction: discord.Interaction):
        """Display current server settings"""
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
                embed=create_error_embed("You need administrator permissions to view settings"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            guild_name = interaction.guild.name

            # Ensure server exists
            await self._ensure_server_exists(guild_id, guild_name)

            # Get settings
            settings = db.get_server_settings(guild_id)

            if settings is None:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to retrieve server settings"),
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=f"Server Settings - {settings['guild_name']}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(
                name="Server Name",
                value=settings['guild_name'],
                inline=False
            )

            embed.add_field(
                name="Command Prefix",
                value=settings['prefix'],
                inline=True
            )

            embed.add_field(
                name="Default Volume",
                value=f"{settings['default_volume']}%",
                inline=True
            )

            # Notification channel
            channel_id = settings['notification_channel_id']
            if channel_id:
                channel = interaction.guild.get_channel(int(channel_id))
                channel_mention = channel.mention if channel else f"<#{channel_id}> (deleted)"
            else:
                channel_mention = "Not set"

            embed.add_field(
                name="Notification Channel",
                value=channel_mention,
                inline=False
            )

            embed.add_field(
                name="Created At",
                value=settings['created_at'],
                inline=True
            )

            embed.add_field(
                name="Last Updated",
                value=settings['updated_at'],
                inline=True
            )

            embed.set_footer(text=f"Server ID: {guild_id}")

            await interaction.response.send_message(embed=embed)

            # Log command
            db.log_command(guild_id, str(interaction.user.id), "settings view")

        except Exception as e:
            logger.error(f"Error in settings view command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to display settings", str(e)),
                ephemeral=True
            )

    @settings_group.command(name="set-prefix", description="Set custom command prefix")
    @app_commands.describe(prefix="New command prefix (default: /)")
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        """Set custom command prefix"""
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
                embed=create_error_embed("You need administrator permissions to change settings"),
                ephemeral=True
            )
            return

        # Validate prefix
        if len(prefix) > 5:
            await interaction.response.send_message(
                embed=create_error_embed("Prefix must be 5 characters or less"),
                ephemeral=True
            )
            return

        if not prefix.strip():
            await interaction.response.send_message(
                embed=create_error_embed("Prefix cannot be empty"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            guild_name = interaction.guild.name

            # Ensure server exists
            await self._ensure_server_exists(guild_id, guild_name)

            # Update prefix
            success = db.update_server_settings(guild_id, prefix=prefix)

            if success:
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "Prefix Updated",
                        f"Command prefix has been set to: `{prefix}`"
                    )
                )

                # Log command
                db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "settings set-prefix",
                    f"New prefix: {prefix}"
                )

                logger.info(f"Prefix updated to '{prefix}' in guild {guild_id}")
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to update prefix"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in set-prefix command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to update prefix", str(e)),
                ephemeral=True
            )

    @settings_group.command(name="set-volume", description="Set default music volume")
    @app_commands.describe(volume="Default volume (0-100)")
    async def set_volume(self, interaction: discord.Interaction, volume: int):
        """Set default music volume"""
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
                embed=create_error_embed("You need administrator permissions to change settings"),
                ephemeral=True
            )
            return

        # Validate volume
        if not 0 <= volume <= 100:
            await interaction.response.send_message(
                embed=create_error_embed("Volume must be between 0 and 100"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            guild_name = interaction.guild.name

            # Ensure server exists
            await self._ensure_server_exists(guild_id, guild_name)

            # Update volume
            success = db.update_server_settings(guild_id, default_volume=volume)

            if success:
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "Volume Updated",
                        f"Default music volume has been set to: {volume}%"
                    )
                )

                # Log command
                db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "settings set-volume",
                    f"New volume: {volume}"
                )

                logger.info(f"Default volume updated to {volume}% in guild {guild_id}")
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to update volume"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in set-volume command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to update volume", str(e)),
                ephemeral=True
            )

    @settings_group.command(name="set-notification-channel", description="Set notification channel")
    @app_commands.describe(channel="Channel where bot notifications will be sent")
    async def set_notification_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Set notification channel"""
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
                embed=create_error_embed("You need administrator permissions to change settings"),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild.id)
            guild_name = interaction.guild.name

            # Ensure server exists
            await self._ensure_server_exists(guild_id, guild_name)

            # Update notification channel
            success = db.update_server_settings(
                guild_id,
                notification_channel_id=str(channel.id)
            )

            if success:
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "Notification Channel Updated",
                        f"Bot notifications will now be sent to: {channel.mention}"
                    )
                )

                # Log command
                db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "settings set-notification-channel",
                    f"New channel: {channel.name} ({channel.id})"
                )

                logger.info(f"Notification channel updated to {channel.name} in guild {guild_id}")
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to update notification channel"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in set-notification-channel command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to update notification channel", str(e)),
                ephemeral=True
            )

    @settings_group.command(name="reset", description="Reset to default settings")
    async def reset_settings(self, interaction: discord.Interaction):
        """Reset to default settings"""
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
                embed=create_error_embed("You need administrator permissions to reset settings"),
                ephemeral=True
            )
            return

        try:
            # Create confirmation view
            view = ConfirmView(interaction.user.id)

            embed = discord.Embed(
                title="Confirm Settings Reset",
                description="Are you sure you want to reset all server settings to defaults?\n\n"
                           "**This will reset:**\n"
                           "- Command prefix to `/`\n"
                           "- Default volume to 50%\n"
                           "- Clear notification channel\n\n"
                           "This action cannot be undone!",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            # Wait for confirmation
            await view.wait()

            if view.value is None:
                # Timeout
                await interaction.edit_original_response(
                    embed=create_error_embed("Confirmation timeout", "Settings reset cancelled"),
                    view=None
                )
                return

            if not view.value:
                # Cancelled
                await interaction.edit_original_response(
                    embed=create_success_embed("Cancelled", "Settings reset cancelled"),
                    view=None
                )
                return

            # Reset settings
            guild_id = str(interaction.guild.id)
            guild_name = interaction.guild.name

            success = db.update_server_settings(
                guild_id,
                prefix='/',
                default_volume=50,
                notification_channel_id=None
            )

            if success:
                await interaction.edit_original_response(
                    embed=create_success_embed(
                        "Settings Reset",
                        "All server settings have been reset to defaults"
                    ),
                    view=None
                )

                # Log command
                db.log_command(
                    guild_id,
                    str(interaction.user.id),
                    "settings reset",
                    "All settings reset to defaults"
                )

                logger.info(f"Settings reset to defaults in guild {guild_id}")
            else:
                await interaction.edit_original_response(
                    embed=create_error_embed("Failed to reset settings"),
                    view=None
                )

        except Exception as e:
            logger.error(f"Error in reset-settings command: {str(e)}")
            await interaction.edit_original_response(
                embed=create_error_embed("Failed to reset settings", str(e)),
                view=None
            )

    @settings_group.command(name="admin-list", description="Show bot administrators")
    async def admin_list(self, interaction: discord.Interaction):
        """Show bot administrators"""
        # DM check
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("This command can only be used in a server"),
                ephemeral=True
            )
            return

        try:
            # Get all members with administrator permission
            admins = [
                member for member in interaction.guild.members
                if member.guild_permissions.administrator and not member.bot
            ]

            if not admins:
                await interaction.response.send_message(
                    embed=create_error_embed("No administrators found"),
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=f"Server Administrators - {interaction.guild.name}",
                description=f"Users with administrator permissions who can change bot settings",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )

            # Add administrators
            admin_list = []
            for admin in admins:
                status_emoji = "🟢" if admin.status == discord.Status.online else "⚫"
                admin_list.append(f"{status_emoji} {admin.mention} (`{admin.id}`)")

            # Split into chunks if too many admins
            if len(admin_list) > 25:
                # Show first 25
                embed.add_field(
                    name=f"Administrators ({len(admin_list)} total)",
                    value="\n".join(admin_list[:25]) + f"\n\n*...and {len(admin_list) - 25} more*",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"Administrators ({len(admin_list)})",
                    value="\n".join(admin_list),
                    inline=False
                )

            embed.set_footer(text=f"Server ID: {interaction.guild.id}")

            await interaction.response.send_message(embed=embed)

            # Log command
            guild_id = str(interaction.guild.id)
            db.log_command(guild_id, str(interaction.user.id), "settings admin-list")

        except Exception as e:
            logger.error(f"Error in admin-list command: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("Failed to retrieve administrator list", str(e)),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
