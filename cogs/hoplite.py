import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup
from utils.logger import setup_logger
from utils.helpers import create_error_embed, create_success_embed

logger = setup_logger(__name__)

# Hoplite API configuration
HOPLITE_API_BASE = "https://status.hoplite.gg"
HOPLITE_SUMMARY_URL = f"{HOPLITE_API_BASE}/summary.json"
HOPLITE_COMPONENTS_URL = f"{HOPLITE_API_BASE}/v2/components.json"
HOPLITE_TRACKER_BASE = "https://www.hoplitetracker.com"
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


class HopliteTrackerAPI:
    """Hoplite Tracker scraping API for retrieving player statistics"""

    def __init__(self):
        self.base_url = HOPLITE_TRACKER_BASE
        self.timeout = aiohttp.ClientTimeout(total=15)
        self._cache = {}
        self._cache_time = {}

    async def get_player_stats(self, player_name: str, game_mode: str = "battle-royale",
                               use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get player statistics from Hoplite Tracker

        Args:
            player_name: Player's username
            game_mode: Game mode (battle-royale, civilization)
            use_cache: Whether to use cached data

        Returns:
            Dictionary with player statistics or None if error
        """
        cache_key = f"{player_name}:{game_mode}"

        if use_cache and self._is_cache_valid(cache_key):
            logger.debug(f"Using cached player data for {player_name}")
            return self._cache.get(cache_key)

        try:
            url = f"{self.base_url}/player/{player_name}/{game_mode}"

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }) as response:
                    if response.status == 200:
                        html = await response.text()
                        stats = await self._parse_player_page(html, player_name, game_mode)

                        if stats:
                            self._cache[cache_key] = stats
                            self._cache_time[cache_key] = datetime.now()
                            logger.info(f"Successfully fetched player stats for {player_name}")
                            return stats
                        else:
                            logger.warning(f"Failed to parse player page for {player_name}")
                            return None
                    elif response.status == 404:
                        logger.warning(f"Player {player_name} not found")
                        return None
                    else:
                        logger.error(f"Hoplite Tracker returned status {response.status} for {player_name}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching player stats for {player_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching player stats for {player_name}: {e}")
            return None

    async def _parse_player_page(self, html: str, player_name: str,
                                 game_mode: str) -> Optional[Dict[str, Any]]:
        """
        Parse player statistics from HTML page

        Args:
            html: HTML content of the player page
            player_name: Player name
            game_mode: Game mode

        Returns:
            Dictionary with extracted statistics or None
        """
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Extract player data from JSON script tags (Next.js pattern)
            stats_data = {
                'player_name': player_name,
                'game_mode': game_mode,
                'wins': 0,
                'kills': 0,
                'kd_ratio': 0.0,
                'games_played': 0,
                'top_kits': [],
                'statistics': {},
                'fetched_at': datetime.now().isoformat()
            }

            # Try to find statistics in script tags
            scripts = soup.find_all('script', {'type': 'application/json'})

            for script in scripts:
                try:
                    data = json.loads(script.string)
                    # Try to find player statistics in the JSON data
                    stats_data.update(self._extract_stats_from_json(data, stats_data))
                except (json.JSONDecodeError, AttributeError):
                    continue

            # If no data found in JSON, try parsing visible HTML elements
            if stats_data['wins'] == 0 and stats_data['kills'] == 0:
                # Look for common patterns in stat displays
                stat_elements = soup.find_all(['span', 'div', 'p'])
                for elem in stat_elements:
                    text = elem.get_text(strip=True)
                    if 'wins' in text.lower():
                        stats_data = self._extract_stat_from_text(text, stats_data, 'wins')
                    elif 'kills' in text.lower():
                        stats_data = self._extract_stat_from_text(text, stats_data, 'kills')
                    elif 'kd' in text.lower() or 'k/d' in text.lower():
                        stats_data = self._extract_stat_from_text(text, stats_data, 'kd_ratio')

            return stats_data if (stats_data['wins'] > 0 or stats_data['kills'] > 0) else None

        except Exception as e:
            logger.error(f"Error parsing player page: {e}")
            return None

    def _extract_stats_from_json(self, data: Any, stats_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract statistics from JSON data"""
        result = {}

        if isinstance(data, dict):
            # Look for common stat keys
            for key, value in data.items():
                if key.lower() in ['wins', 'victories', 'win_count']:
                    result['wins'] = int(value) if isinstance(value, (int, str)) else 0
                elif key.lower() in ['kills', 'kill_count', 'total_kills']:
                    result['kills'] = int(value) if isinstance(value, (int, str)) else 0
                elif key.lower() in ['kd', 'kd_ratio', 'k_d_ratio']:
                    try:
                        result['kd_ratio'] = float(value) if value else 0.0
                    except (ValueError, TypeError):
                        result['kd_ratio'] = 0.0
                elif key.lower() in ['games', 'games_played', 'matches']:
                    result['games_played'] = int(value) if isinstance(value, (int, str)) else 0
                elif key.lower() in ['kits', 'top_kits', 'kit_stats']:
                    if isinstance(value, list):
                        result['top_kits'] = value[:5]  # Top 5 kits

        return result

    def _extract_stat_from_text(self, text: str, stats_data: Dict[str, Any],
                                stat_type: str) -> Dict[str, Any]:
        """Extract statistic from text content"""
        import re

        # Try to extract numbers from text
        numbers = re.findall(r'\d+(?:[.,]\d+)?', text)

        if numbers:
            try:
                value = numbers[0].replace(',', '')
                if stat_type == 'wins':
                    stats_data['wins'] = int(float(value))
                elif stat_type == 'kills':
                    stats_data['kills'] = int(float(value))
                elif stat_type == 'kd_ratio':
                    stats_data['kd_ratio'] = float(value)
            except (ValueError, IndexError):
                pass

        return stats_data

    def _is_cache_valid(self, key: str, max_age_seconds: int = 3600) -> bool:
        """Check if cached data is still valid (1 hour)"""
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
        self.tracker_api = HopliteTrackerAPI()
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

    @hoplite_group.command(name="player", description="Get player statistics from Hoplite Tracker")
    @app_commands.describe(
        player_name="Player's username",
        game_mode="Game mode (battle-royale or civilization)"
    )
    async def hoplite_player(self, interaction: discord.Interaction, player_name: str,
                             game_mode: str = "battle-royale"):
        """Get player statistics from Hoplite Tracker"""
        await interaction.response.defer()

        try:
            # Validate game mode
            if game_mode.lower() not in ["battle-royale", "civilization", "br"]:
                if game_mode.lower() == "br":
                    game_mode = "battle-royale"
                else:
                    game_mode = "battle-royale"  # Default to battle-royale

            logger.info(f"Player stats requested for {player_name} ({game_mode}) by {interaction.user}")

            # Get player stats
            stats = await self.tracker_api.get_player_stats(player_name, game_mode, use_cache=False)

            if not stats:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "Player not found",
                        f"Could not find player '{player_name}' on Hoplite Tracker.\n"
                        f"Please check the spelling and try again."
                    ),
                    ephemeral=True
                )
                return

            # Create player stats embed
            embed = discord.Embed(
                title=f"📊 {stats['player_name']} - Stats",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            # Add basic stats
            embed.add_field(
                name="Wins",
                value=f"🏆 {stats['wins']:,}",
                inline=True
            )

            embed.add_field(
                name="Kills",
                value=f"⚔️ {stats['kills']:,}",
                inline=True
            )

            # Calculate K/D ratio
            kd_ratio = stats.get('kd_ratio', 0.0)
            if kd_ratio == 0.0 and stats['kills'] > 0 and stats['games_played'] > 0:
                kd_ratio = stats['kills'] / max(1, stats['games_played'])

            embed.add_field(
                name="K/D Ratio",
                value=f"📈 {kd_ratio:.2f}",
                inline=True
            )

            # Add games played
            if stats['games_played'] > 0:
                embed.add_field(
                    name="Games Played",
                    value=f"🎮 {stats['games_played']:,}",
                    inline=True
                )

            # Calculate win rate
            if stats['games_played'] > 0:
                win_rate = (stats['wins'] / stats['games_played']) * 100
                embed.add_field(
                    name="Win Rate",
                    value=f"📊 {win_rate:.1f}%",
                    inline=True
                )

            # Add game mode info
            mode_display = "Battle Royale" if game_mode == "battle-royale" else "Civilization"
            embed.add_field(
                name="Game Mode",
                value=f"🎯 {mode_display}",
                inline=True
            )

            # Add top kits if available
            if stats.get('top_kits'):
                kits_text = ", ".join(str(kit) for kit in stats['top_kits'][:5])
                embed.add_field(
                    name="Top Kits",
                    value=kits_text if kits_text else "N/A",
                    inline=False
                )

            embed.set_footer(text=f"Data from Hoplite Tracker | Requested by {interaction.user}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in hoplite player command: {e}")
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
