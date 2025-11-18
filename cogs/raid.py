import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from utils.logger import setup_logger
from utils.helpers import create_error_embed, create_success_embed

logger = setup_logger(__name__)

# EarthMC API configuration
EARTHMC_API_BASE = "https://api.earthmc.net/v3/aurora"
EARTHMC_TOWNS_ENDPOINT = f"{EARTHMC_API_BASE}/towns"

RAID_CHECK_INTERVAL = 1800  # 30 minutes in seconds


class RaidAPI:
    """EarthMC Raid API wrapper for retrieving ruins information"""

    def __init__(self):
        self.base_url = EARTHMC_API_BASE
        self.timeout = aiohttp.ClientTimeout(total=30)  # Extended timeout for batch processing
        self._cache = {}
        self._cache_time = {}

    async def get_all_towns(self, use_cache: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Get all towns from the server with timestamps

        Args:
            use_cache: Whether to use cached data

        Returns:
            List of town dictionaries with timestamps or None if error
        """
        if use_cache and self._is_cache_valid('all_towns'):
            logger.debug("Using cached all towns data")
            return self._cache.get('all_towns')

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Step 1: Get all town names from the list endpoint
                async with session.get(EARTHMC_TOWNS_ENDPOINT) as response:
                    if response.status != 200:
                        logger.error(f"EarthMC API returned status {response.status}")
                        return None

                    town_list = await response.json()
                    if not isinstance(town_list, list):
                        logger.warning("Unexpected response format from towns endpoint")
                        return None

                # Step 2: Get detailed information for all towns in batches
                batch_size = 100
                all_towns_detailed = []
                town_names = [t['name'] for t in town_list]

                logger.info(f"Fetching details for {len(town_names)} towns in batches of {batch_size}")

                for i in range(0, len(town_names), batch_size):
                    batch = town_names[i:i+batch_size]
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(town_names) + batch_size - 1) // batch_size

                    try:
                        async with session.post(EARTHMC_TOWNS_ENDPOINT, json={"query": batch}) as batch_response:
                            if batch_response.status == 200:
                                batch_data = await batch_response.json()
                                if isinstance(batch_data, list):
                                    all_towns_detailed.extend(batch_data)
                                    logger.debug(f"Batch {batch_num}/{total_batches}: Retrieved {len(batch_data)} towns")
                                else:
                                    logger.warning(f"Batch {batch_num}/{total_batches}: Unexpected response type: {type(batch_data)}")
                            else:
                                logger.warning(f"Batch {batch_num}/{total_batches}: API returned status {batch_response.status}")
                    except Exception as batch_error:
                        logger.error(f"Batch {batch_num}/{total_batches}: Error - {batch_error}")

                if all_towns_detailed:
                    self._cache['all_towns'] = all_towns_detailed
                    self._cache_time['all_towns'] = datetime.now()
                    logger.info(f"Successfully fetched {len(all_towns_detailed)} towns with timestamps")
                    return all_towns_detailed
                else:
                    logger.warning(f"No town data retrieved from API (got {len(town_list)} town names but 0 detailed records)")
                    return None

        except asyncio.TimeoutError:
            logger.error("Timeout while fetching all towns")
            return None
        except Exception as e:
            logger.error(f"Error fetching all towns: {e}")
            return None

    def get_ruining_towns(self, towns: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get towns that are about to ruin, sorted by ruin date

        Args:
            towns: List of all towns
            limit: Maximum number of towns to return

        Returns:
            List of towns sorted by ruin date
        """
        ruining_towns = []

        for town in towns:
            # Check if town has ruined timestamp
            if 'timestamps' in town and town['timestamps']:
                ruined_at = town['timestamps'].get('ruinedAt')
                if ruined_at:
                    ruining_towns.append(town)

        # Sort by ruined date (earliest first)
        ruining_towns.sort(
            key=lambda t: t.get('timestamps', {}).get('ruinedAt', float('inf'))
        )

        return ruining_towns[:limit]

    async def get_inactive_mayor_towns(self, towns: List[Dict[str, Any]], days: int = 40, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get towns whose mayors have not logged in for specified days

        Args:
            towns: List of all towns
            days: Number of days for inactivity threshold
            limit: Maximum number of towns to return

        Returns:
            List of towns with inactive mayors
        """
        from time import time

        inactive_towns = []
        current_time_ms = int(time() * 1000)  # Current time in milliseconds
        inactivity_threshold_ms = days * 24 * 60 * 60 * 1000  # Convert days to milliseconds

        try:
            # Step 1: Extract unique mayor names from all towns
            mayor_names = set()
            town_by_mayor = {}  # Map mayor name to towns

            for town in towns:
                mayor_info = town.get('mayor', {})
                if not mayor_info or not isinstance(mayor_info, dict):
                    continue

                mayor_name = mayor_info.get('name')
                if not mayor_name:
                    continue

                mayor_names.add(mayor_name)
                if mayor_name not in town_by_mayor:
                    town_by_mayor[mayor_name] = []
                town_by_mayor[mayor_name].append(town)

            logger.info(f"Found {len(mayor_names)} unique mayors to check for inactivity")

            # Step 2: Fetch mayor data in batches
            mayors_data = {}  # Map mayor name to player data
            batch_size = 100
            mayors_list = list(mayor_names)
            players_endpoint = f"{self.base_url}/players"

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                for i in range(0, len(mayors_list), batch_size):
                    batch = mayors_list[i:i+batch_size]
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(mayors_list) + batch_size - 1) // batch_size

                    try:
                        async with session.post(players_endpoint, json={"query": batch}) as response:
                            if response.status == 200:
                                player_data = await response.json()
                                if isinstance(player_data, list):
                                    for player in player_data:
                                        player_name = player.get('name')
                                        if player_name:
                                            mayors_data[player_name] = player
                                    logger.debug(f"Batch {batch_num}/{total_batches}: Retrieved {len(player_data)} mayors")
                            else:
                                logger.warning(f"Batch {batch_num}/{total_batches}: API returned status {response.status}")
                    except Exception as batch_error:
                        logger.error(f"Batch {batch_num}/{total_batches}: Error - {batch_error}")

                # Step 3: Check inactivity for each mayor's towns
                for mayor_name, mayor_data in mayors_data.items():
                    last_online = mayor_data.get('timestamps', {}).get('lastOnline')

                    if last_online:
                        # Convert to milliseconds if needed
                        if last_online < 10000000000:
                            last_online = last_online * 1000

                        time_inactive = current_time_ms - last_online

                        if time_inactive >= inactivity_threshold_ms:
                            # Add all towns of this mayor to inactive list
                            for town in town_by_mayor.get(mayor_name, []):
                                town_copy = town.copy()
                                town_copy['mayor_inactive_days'] = time_inactive // (24 * 60 * 60 * 1000)
                                inactive_towns.append(town_copy)

                # Sort by inactivity days (most inactive first)
                inactive_towns.sort(key=lambda t: t.get('mayor_inactive_days', 0), reverse=True)
                logger.info(f"Found {len(inactive_towns)} towns with inactive mayors ({days}+ days)")
                return inactive_towns[:limit]

        except Exception as e:
            logger.error(f"Error fetching inactive mayor towns: {e}")
            return []

    def _is_cache_valid(self, key: str, max_age_seconds: int = 300) -> bool:
        """Check if cached data is still valid (5 minutes default)"""
        if key not in self._cache or key not in self._cache_time:
            return False

        age = (datetime.now() - self._cache_time[key]).total_seconds()
        return age < max_age_seconds

    def clear_cache(self):
        """Clear all cached data"""
        self._cache.clear()
        self._cache_time.clear()


class RaidCog(commands.Cog):
    """Raid monitoring commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = RaidAPI()
        self.db = None

        # Start the raid monitoring task
        self.monitor_raids.start()

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monitor_raids.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize database when bot is ready"""
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()
        logger.info("Raid cog is ready")

    # ==================== SLASH COMMANDS ====================

    @app_commands.command(name="raid", description="市長が非アクティブなタウン（ruins予定）を表示")
    @app_commands.describe(
        limit="表示するタウン数 (デフォルト: 20)",
        mode="表示モード: inactive-mayor=市長が非アクティブ (デフォルト), ruining=既に崩壊済み"
    )
    async def raid(self, interaction: discord.Interaction, limit: int = 20, mode: str = "inactive-mayor"):
        """Display towns about to ruin (mayors inactive 40+ days) or already ruined"""
        await interaction.response.defer()

        try:
            logger.info(f"Raid info requested by {interaction.user} (mode: {mode})")

            # Get all towns
            towns = await self.api.get_all_towns(use_cache=False)

            if not towns:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "情報取得失敗",
                        "タウン情報を取得できませんでした。後でもう一度試してください。"
                    ),
                    ephemeral=True
                )
                return

            # Get towns based on mode
            if mode.lower() == "ruining":
                # Already ruined towns
                towns_to_display = self.api.get_ruining_towns(towns, limit=limit)
                title = "⚔️ 既に崩壊したタウン"
                empty_message = "既に崩壊したタウンはありません。"
                data_key = "ruinedAt"
                date_label = "崩壊日"
            else:
                # Default to inactive mayors (upcoming ruins)
                await interaction.followup.send(
                    content="⏳ 市長が非アクティブなタウンを取得中...",
                    ephemeral=True
                )
                towns_to_display = await self.api.get_inactive_mayor_towns(towns, days=40, limit=limit)
                title = "👻 崩壊予定タウン (市長が40日以上ログインなし)"
                empty_message = "市長が40日以上ログインしていないタウンはありません。"
                data_key = "mayor_inactive_days"
                date_label = "市長が非アクティブな日数"

            if not towns_to_display:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "該当するタウンなし",
                        empty_message
                    ),
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=title,
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )

            # Helper function to format timestamp
            def format_timestamp(timestamp) -> str:
                try:
                    if isinstance(timestamp, (int, float)):
                        if timestamp > 10000000000:
                            timestamp = timestamp / 1000
                        dt = datetime.fromtimestamp(timestamp)
                        return dt.strftime("%Y年%m月%d日 %H:%M:%S")
                    else:
                        return str(timestamp)
                except Exception as e:
                    logger.warning(f"Failed to convert timestamp {timestamp}: {e}")
                    return str(timestamp)

            # Split towns into chunks to avoid embed limits
            chunk_size = 10
            for i in range(0, len(towns_to_display), chunk_size):
                chunk = towns_to_display[i:i+chunk_size]
                towns_text = ""

                for town in chunk:
                    town_name = town.get('name', 'Unknown')
                    nation_info = town.get('nation', {})
                    nation_name = nation_info.get('name', '独立') if isinstance(nation_info, dict) else nation_info or '独立'
                    mayor = town.get('mayor', {})
                    mayor_name = mayor.get('name', 'Unknown') if isinstance(mayor, dict) else mayor

                    towns_text += f"**{town_name}** (`{nation_name}`)\n"
                    towns_text += f"  市長: `{mayor_name}`\n"

                    # Display different information based on mode
                    if mode.lower() == "inactive-mayor":
                        inactive_days = town.get('mayor_inactive_days', 0)
                        towns_text += f"  非アクティブ日数: `{inactive_days}日`\n\n"
                    else:
                        ruin_date = town.get('timestamps', {}).get('ruinedAt')
                        ruin_date_str = format_timestamp(ruin_date) if ruin_date else "不明"
                        towns_text += f"  崩壊予定: `{ruin_date_str}`\n\n"

                field_name = f"🏴 タウン ({i+1}-{min(i+chunk_size, len(towns_to_display))})"
                embed.add_field(name=field_name, value=towns_text.rstrip("\n"), inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in raid command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="raid-enable", description="Raid 通知を有効化")
    @app_commands.describe(channel="通知を送信するチャネル")
    async def raid_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Enable Raid notifications"""
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()

        # Check permissions
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "権限がありません",
                    f"{channel.mention} へのメッセージ送信権限がありません。"
                ),
                ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "権限がありません",
                    "このコマンドを実行するには「サーバー管理」権限が必要です。"
                ),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild_id)
            channel_id = str(channel.id)

            if self.db.setup_raid_notifications(guild_id, channel_id):
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "通知を有効化しました",
                        f"Raid 通知が30分ごとに {channel.mention} に送信されます。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("有効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error enabling Raid notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="raid-disable", description="Raid 通知を無効化")
    async def raid_disable(self, interaction: discord.Interaction):
        """Disable Raid notifications"""
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "権限がありません",
                    "このコマンドを実行するには「サーバー管理」権限が必要です。"
                ),
                ephemeral=True
            )
            return

        try:
            guild_id = str(interaction.guild_id)

            if self.db.disable_raid_notifications(guild_id):
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "通知を無効化しました",
                        "このサーバーでの Raid 通知が停止されました。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("無効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error disabling Raid notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    # ==================== MONITORING TASK ====================

    @tasks.loop(seconds=RAID_CHECK_INTERVAL)
    async def monitor_raids(self):
        """Periodically check and notify about ruin times"""
        if self.db is None:
            logger.debug("Raid monitoring: Database not initialized")
            return

        try:
            logger.info("Starting raid monitoring task...")
            # Get all towns
            towns = await self.api.get_all_towns(use_cache=False)

            if not towns:
                logger.warning("Raid monitoring: Failed to fetch towns from API (returned None or empty)")
                return

            if len(towns) == 0:
                logger.warning("Raid monitoring: Retrieved 0 towns from API")

            # Get ruining towns
            ruining_towns = self.api.get_ruining_towns(towns, limit=20)

            # Get all active notification channels
            notification_channels = self.db.get_all_raid_notifications()

            for config in notification_channels:
                try:
                    channel_id = int(config['channel_id'])
                    guild_id = config['guild_id']

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
                        continue

                    # Create and send notification
                    await self._send_raid_notification(channel, ruining_towns)

                    # Update notification time
                    self.db.update_raid_notification_time(guild_id)

                except Exception as e:
                    logger.error(f"Error sending Raid notification: {e}")

        except Exception as e:
            logger.error(f"Error in monitor_raids task: {e}")

    @monitor_raids.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready before starting monitoring"""
        await self.bot.wait_until_ready()
        logger.info("EarthMC Raid monitoring task started")

    async def _send_raid_notification(self, channel: discord.TextChannel, ruining_towns: List[Dict[str, Any]]):
        """Send Raid notification to a channel"""
        try:
            if not ruining_towns:
                return

            embed = discord.Embed(
                title="⚔️ 崩壊予定タウン",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )

            # Helper function to format timestamp
            def format_timestamp(timestamp) -> str:
                try:
                    if isinstance(timestamp, (int, float)):
                        if timestamp > 10000000000:
                            timestamp = timestamp / 1000
                        dt = datetime.fromtimestamp(timestamp)
                        return dt.strftime("%Y年%m月%d日 %H:%M:%S")
                    else:
                        return str(timestamp)
                except Exception as e:
                    logger.warning(f"Failed to convert timestamp {timestamp}: {e}")
                    return str(timestamp)

            # Split towns into chunks
            chunk_size = 10
            for i in range(0, len(ruining_towns), chunk_size):
                chunk = ruining_towns[i:i+chunk_size]
                towns_text = ""

                for town in chunk:
                    town_name = town.get('name', 'Unknown')
                    nation_info = town.get('nation', {})
                    nation_name = nation_info.get('name', '独立') if isinstance(nation_info, dict) else nation_info or '独立'
                    mayor = town.get('mayor', {})
                    mayor_name = mayor.get('name', 'Unknown') if isinstance(mayor, dict) else mayor
                    ruin_date = town.get('timestamps', {}).get('ruinedAt')
                    ruin_date_str = format_timestamp(ruin_date) if ruin_date else "不明"

                    towns_text += f"**{town_name}** (`{nation_name}`)\n"
                    towns_text += f"  市長: `{mayor_name}`\n"
                    towns_text += f"  崩壊予定: `{ruin_date_str}`\n\n"

                field_name = f"🏴 タウン ({i+1}-{min(i+chunk_size, len(ruining_towns))})"
                embed.add_field(name=field_name, value=towns_text.rstrip("\n"), inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await channel.send(embed=embed)
            logger.info(f"Raid notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending Raid notification: {e}")


async def setup(bot: commands.Bot):
    """Load the Raid cog"""
    cog = RaidCog(bot)
    await bot.add_cog(cog)
    logger.info("Raid cog loaded successfully")
