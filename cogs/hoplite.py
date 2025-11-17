import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from utils.logger import setup_logger
from utils.helpers import create_error_embed, create_success_embed

logger = setup_logger(__name__)

# Hoplite API configuration
HOPLITE_API_BASE = "https://status.hoplite.gg"
HOPLITE_SUMMARY_URL = f"{HOPLITE_API_BASE}/summary.json"
HOPLITE_COMPONENTS_URL = f"{HOPLITE_API_BASE}/v2/components.json"
POLLING_INTERVAL = 300  # 5 minutes in seconds


class HopliteAPI:
    """Hoplite Status API wrapper for retrieving service status"""

    def __init__(self):
        self.base_url = HOPLITE_API_BASE
        self.summary_url = HOPLITE_SUMMARY_URL
        self.components_url = HOPLITE_COMPONENTS_URL
        self.timeout = aiohttp.ClientTimeout(total=10)
        self._cache = {}
        self._cache_time = {}

    async def get_status(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get overall Hoplite status

        Args:
            use_cache: Whether to use cached data if available

        Returns:
            Dictionary with status information or None if error
        """
        if use_cache and self._is_cache_valid('status'):
            logger.debug("Using cached status data")
            return self._cache.get('status')

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.summary_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache['status'] = data
                        self._cache_time['status'] = datetime.now()
                        logger.info("Successfully fetched Hoplite status")
                        return data
                    else:
                        logger.error(f"Hoplite API returned status {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.error("Timeout while fetching Hoplite status")
            return None
        except Exception as e:
            logger.error(f"Error fetching Hoplite status: {e}")
            return None

    async def get_components(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get Hoplite component status

        Args:
            use_cache: Whether to use cached data if available

        Returns:
            Dictionary with component information or None if error
        """
        if use_cache and self._is_cache_valid('components'):
            logger.debug("Using cached components data")
            return self._cache.get('components')

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.components_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache['components'] = data
                        self._cache_time['components'] = datetime.now()
                        logger.info("Successfully fetched Hoplite components")
                        return data
                    else:
                        logger.error(f"Hoplite API returned status {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.error("Timeout while fetching Hoplite components")
            return None
        except Exception as e:
            logger.error(f"Error fetching Hoplite components: {e}")
            return None

    def _is_cache_valid(self, key: str, max_age_seconds: int = 60) -> bool:
        """Check if cached data is still valid"""
        if key not in self._cache or key not in self._cache_time:
            return False

        age = (datetime.now() - self._cache_time[key]).total_seconds()
        return age < max_age_seconds

    def clear_cache(self):
        """Clear all cached data"""
        self._cache.clear()
        self._cache_time.clear()


class HopliteCog(commands.Cog):
    """Hoplite status monitoring commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = HopliteAPI()
        self.db = None

        # Start the monitoring task
        self.monitor_hoplite_status.start()

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monitor_hoplite_status.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize database when bot is ready"""
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()
        logger.info("Hoplite cog is ready")

    # ==================== SLASH COMMANDS ====================

    hoplite_group = app_commands.Group(name="hoplite", description="Hoplite status monitoring commands")

    @hoplite_group.command(name="status", description="Check current Hoplite status")
    async def hoplite_status(self, interaction: discord.Interaction):
        """Display current Hoplite service status"""
        await interaction.response.defer()

        try:
            logger.info(f"Status check requested by {interaction.user} in guild {interaction.guild_id}")

            status_data = await self.api.get_status(use_cache=False)

            if not status_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "Failed to fetch status",
                        "Could not retrieve Hoplite status. Please try again later."
                    ),
                    ephemeral=True
                )
                return

            # Extract page status
            page = status_data.get('page', {})
            components = status_data.get('components', [])
            incidents = status_data.get('incidents', [])

            # Determine overall status
            status_indicator = page.get('status', 'unknown')
            status_color = self._get_status_color(status_indicator)

            embed = discord.Embed(
                title="🌐 Hoplite Service Status",
                color=status_color,
                timestamp=discord.utils.utcnow()
            )

            # Overall status
            embed.add_field(
                name="Overall Status",
                value=self._format_status(status_indicator),
                inline=False
            )

            # Component statuses
            if components:
                component_status = self._format_components(components)
                if component_status:
                    embed.add_field(
                        name="Components",
                        value=component_status,
                        inline=False
                    )

            # Active incidents
            if incidents:
                incident_text = f"⚠️ **{len(incidents)} Active Incident(s)**\n"
                for incident in incidents[:3]:  # Show max 3 incidents
                    incident_text += f"• {incident.get('name', 'Unknown')}\n"
                if len(incidents) > 3:
                    incident_text += f"• ... and {len(incidents) - 3} more"

                embed.add_field(
                    name="Incidents",
                    value=incident_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Incidents",
                    value="✅ No active incidents",
                    inline=False
                )

            # Last updated
            updated_time = page.get('updated_at', 'Unknown')
            embed.set_footer(text=f"Last updated: {updated_time}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in hoplite status command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("An error occurred", str(e)),
                ephemeral=True
            )

    @hoplite_group.command(name="components", description="View detailed component status")
    async def hoplite_components(self, interaction: discord.Interaction):
        """Display detailed Hoplite component information"""
        await interaction.response.defer()

        try:
            logger.info(f"Components check requested by {interaction.user} in guild {interaction.guild_id}")

            components_data = await self.api.get_components(use_cache=False)

            if not components_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "Failed to fetch components",
                        "Could not retrieve Hoplite components. Please try again later."
                    ),
                    ephemeral=True
                )
                return

            components = components_data.get('components', [])

            if not components:
                await interaction.followup.send(
                    embed=create_error_embed("No components found", "No Hoplite components available."),
                    ephemeral=True
                )
                return

            # Create component status embed
            embed = discord.Embed(
                title="📊 Hoplite Component Status",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            for component in components:
                status = component.get('status', 'unknown')
                name = component.get('name', 'Unknown')
                description = component.get('description', '')

                status_emoji = self._get_status_emoji(status)
                field_value = f"{status_emoji} {status.upper()}"

                if description:
                    field_value += f"\n*{description}*"

                embed.add_field(
                    name=name,
                    value=field_value,
                    inline=False
                )

            embed.set_footer(text=f"Total components: {len(components)}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in hoplite components command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("An error occurred", str(e)),
                ephemeral=True
            )

    # Create subcommand group for monitor
    monitor_group = app_commands.Group(name="monitor", description="Manage Hoplite status monitoring")

    @monitor_group.command(name="enable", description="Enable Hoplite status monitoring for this server")
    @app_commands.describe(channel="The channel where notifications will be sent")
    async def monitor_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Enable monitoring and set notification channel"""
        # Initialize database if not already done
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()

        # Check bot permissions
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Missing permissions",
                    f"I don't have permission to send messages in {channel.mention}"
                ),
                ephemeral=True
            )
            return

        # Check user permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Missing permissions",
                    "You need 'Manage Server' permission to use this command"
                ),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild_id)
            channel_id = str(channel.id)

            if self.db.setup_hoplite_monitoring(guild_id, channel_id):
                logger.info(f"Hoplite monitoring enabled for guild {guild_id}")
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "Monitoring enabled",
                        f"Hoplite status monitoring is now active.\nNotifications will be sent to {channel.mention}"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to enable monitoring", "Please try again later"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error enabling monitoring: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("An error occurred", str(e)),
                ephemeral=True
            )

    @monitor_group.command(name="disable", description="Disable Hoplite status monitoring for this server")
    async def monitor_disable(self, interaction: discord.Interaction):
        """Disable monitoring"""
        # Initialize database if not already done
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()

        # Check user permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "Missing permissions",
                    "You need 'Manage Server' permission to use this command"
                ),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild_id)

            if self.db.disable_hoplite_monitoring(guild_id):
                logger.info(f"Hoplite monitoring disabled for guild {guild_id}")
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "Monitoring disabled",
                        "Hoplite status monitoring has been disabled for this server"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("Failed to disable monitoring", "Please try again later"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error disabling monitoring: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("An error occurred", str(e)),
                ephemeral=True
            )

    @monitor_group.command(name="view", description="View current monitoring settings")
    async def monitor_view(self, interaction: discord.Interaction):
        """View monitoring settings"""
        # Initialize database if not already done
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()

        try:
            guild_id = str(interaction.guild_id)

            monitoring_settings = self.db.get_hoplite_monitoring(guild_id)

            if not monitoring_settings:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "Monitoring not configured",
                        "Hoplite status monitoring is not enabled for this server.\n"
                        "Use `/hoplite monitor-enable` to set it up."
                    ),
                    ephemeral=True
                )
                return

            channel = self.bot.get_channel(int(monitoring_settings['channel_id']))
            status = "✅ Enabled" if monitoring_settings['enabled'] else "❌ Disabled"

            embed = discord.Embed(
                title="📋 Monitoring Settings",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(
                name="Notification Channel",
                value=f"{channel.mention}" if channel else "Channel not found",
                inline=False
            )

            last_status = monitoring_settings.get('last_status')
            if last_status:
                embed.add_field(name="Last Known Status", value=last_status, inline=False)

            embed.add_field(
                name="Monitoring Since",
                value=monitoring_settings.get('created_at', 'Unknown'),
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error viewing monitoring settings: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("An error occurred", str(e)),
                ephemeral=True
            )

    # ==================== MONITORING TASK ====================

    @tasks.loop(seconds=POLLING_INTERVAL)
    async def monitor_hoplite_status(self):
        """Periodically monitor Hoplite status and send notifications"""
        if self.db is None:
            return

        try:
            # Get all active monitoring configurations
            monitoring_configs = self.db.get_all_hoplite_monitoring()

            if not monitoring_configs:
                logger.debug("No active Hoplite monitoring configurations")
                return

            # Fetch current status
            status_data = await self.api.get_status(use_cache=False)
            components_data = await self.api.get_components(use_cache=False)

            if not status_data or not components_data:
                logger.warning("Failed to fetch current Hoplite status")
                return

            # Process each monitoring configuration
            for config in monitoring_configs:
                await self._check_and_notify(config, status_data, components_data)

        except Exception as e:
            logger.error(f"Error in monitoring task: {e}")

    @monitor_hoplite_status.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready before starting monitoring"""
        await self.bot.wait_until_ready()
        logger.info("Hoplite monitoring task started")

    async def _check_and_notify(self, config: Dict[str, Any], status_data: Dict[str, Any],
                                components_data: Dict[str, Any]):
        """
        Check for status changes and send notifications

        Args:
            config: Monitoring configuration from database
            status_data: Current Hoplite status data
            components_data: Current Hoplite components data
        """
        try:
            guild_id = config['guild_id']
            channel_id = int(config['channel_id'])

            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
                return

            # Get current page status
            page = status_data.get('page', {})
            current_status = page.get('status', 'unknown')

            # Get previous status
            previous_status = config.get('last_status')

            # Get incidents
            incidents = status_data.get('incidents', [])
            current_incident_ids = [str(inc['id']) for inc in incidents]
            previous_incident_ids = json.loads(config.get('last_incident_ids', '[]'))

            # Check for status change
            if previous_status and previous_status != current_status:
                await self._send_status_change_notification(channel, previous_status, current_status)

            # Check for new incidents
            new_incidents = [inc_id for inc_id in current_incident_ids if inc_id not in previous_incident_ids]
            if new_incidents:
                for incident_id in new_incidents:
                    incident = next((inc for inc in incidents if str(inc['id']) == incident_id), None)
                    if incident:
                        await self._send_incident_notification(channel, incident)

            # Check for resolved incidents
            resolved_incidents = [inc_id for inc_id in previous_incident_ids if inc_id not in current_incident_ids]
            if resolved_incidents:
                for incident_id in resolved_incidents:
                    # Get incident from full data or just show generic resolution message
                    await self._send_incident_resolved_notification(channel, incident_id)

            # Update database
            self.db.update_hoplite_status(
                guild_id,
                current_status,
                json.dumps(current_incident_ids)
            )

        except Exception as e:
            logger.error(f"Error in _check_and_notify: {e}")

    async def _send_status_change_notification(self, channel: discord.TextChannel, from_status: str,
                                               to_status: str):
        """Send status change notification"""
        try:
            from_emoji = self._get_status_emoji(from_status)
            to_emoji = self._get_status_emoji(to_status)

            embed = discord.Embed(
                title="🔔 Hoplite Status Change",
                description=f"{from_emoji} **{from_status.upper()}** → {to_emoji} **{to_status.upper()}**",
                color=self._get_status_color(to_status),
                timestamp=discord.utils.utcnow()
            )

            await channel.send(embed=embed)
            logger.info(f"Status change notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending status change notification: {e}")

    async def _send_incident_notification(self, channel: discord.TextChannel, incident: Dict[str, Any]):
        """Send incident notification"""
        try:
            embed = discord.Embed(
                title="⚠️ Hoplite Incident Reported",
                description=incident.get('name', 'Unknown incident'),
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            status = incident.get('status', 'unknown')
            impact = incident.get('impact', 'unknown')

            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Impact", value=impact, inline=True)

            body = incident.get('body')
            if body:
                # Truncate long descriptions
                if len(body) > 1024:
                    body = body[:1021] + "..."
                embed.add_field(name="Details", value=body, inline=False)

            created_at = incident.get('created_at')
            if created_at:
                embed.set_footer(text=f"Reported: {created_at}")

            await channel.send(embed=embed)
            logger.info(f"Incident notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending incident notification: {e}")

    async def _send_incident_resolved_notification(self, channel: discord.TextChannel, incident_id: str):
        """Send incident resolved notification"""
        try:
            embed = discord.Embed(
                title="✅ Incident Resolved",
                description=f"Incident #{incident_id} has been resolved",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            await channel.send(embed=embed)
            logger.info(f"Incident resolved notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending incident resolved notification: {e}")

    # ==================== HELPER METHODS ====================

    def _get_status_color(self, status: str) -> discord.Color:
        """Get color for status indicator"""
        status_lower = status.lower()
        if status_lower == 'operational':
            return discord.Color.green()
        elif status_lower == 'degraded_performance':
            return discord.Color.gold()
        elif status_lower == 'partial_outage':
            return discord.Color.orange()
        elif status_lower == 'major_outage':
            return discord.Color.red()
        else:
            return discord.Color.greyple()

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status"""
        status_lower = status.lower()
        if status_lower in ['operational', 'ok']:
            return '✅'
        elif status_lower in ['degraded_performance', 'degraded']:
            return '⚠️'
        elif status_lower in ['partial_outage']:
            return '⚠️'
        elif status_lower in ['major_outage', 'down']:
            return '❌'
        elif status_lower in ['investigating', 'monitoring']:
            return '🔍'
        else:
            return '❓'

    def _format_status(self, status: str) -> str:
        """Format status text with emoji"""
        emoji = self._get_status_emoji(status)
        return f"{emoji} {status.replace('_', ' ').title()}"

    def _format_components(self, components: List[Dict[str, Any]]) -> str:
        """Format component list"""
        component_lines = []
        for component in components[:5]:  # Show max 5 components
            name = component.get('name', 'Unknown')
            status = component.get('status', 'unknown')
            emoji = self._get_status_emoji(status)
            component_lines.append(f"{emoji} {name}")

        if len(components) > 5:
            component_lines.append(f"... and {len(components) - 5} more")

        return '\n'.join(component_lines) if component_lines else "No components available"


async def setup(bot: commands.Bot):
    """Load the Hoplite cog"""
    cog = HopliteCog(bot)
    await bot.add_cog(cog)
    logger.info("Hoplite cog loaded successfully")
