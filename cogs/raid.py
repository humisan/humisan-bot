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
        self.timeout = aiohttp.ClientTimeout(total=10)
        self._cache = {}
        self._cache_time = {}

    async def get_all_towns(self, use_cache: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Get all towns from the server

        Args:
            use_cache: Whether to use cached data

        Returns:
            List of town dictionaries or None if error
        """
        if use_cache and self._is_cache_valid('all_towns'):
            logger.debug("Using cached all towns data")
            return self._cache.get('all_towns')

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(EARTHMC_TOWNS_ENDPOINT, json={"query": []}) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            self._cache['all_towns'] = data
                            self._cache_time['all_towns'] = datetime.now()
                            logger.info(f"Successfully fetched {len(data)} towns")
                            return data
                        else:
                            logger.warning("Unexpected response format from towns endpoint")
                            return None
                    else:
                        logger.error(f"EarthMC API returned status {response.status}")
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

    @app_commands.command(name="raid", description="次に崩壊するタウンを表示")
    @app_commands.describe(limit="表示するタウン数 (デフォルト: 20)")
    async def raid(self, interaction: discord.Interaction, limit: int = 20):
        """Display towns about to ruin"""
        await interaction.response.defer()

        try:
            logger.info(f"Raid info requested by {interaction.user}")

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

            # Get ruining towns
            ruining_towns = self.api.get_ruining_towns(towns, limit=limit)

            if not ruining_towns:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "予定中のタウンなし",
                        "現在、崩壊予定のタウンはありません。"
                    ),
                    ephemeral=True
                )
                return

            # Create embed
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

            # Split towns into chunks to avoid embed limits
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
            return

        try:
            # Get all towns
            towns = await self.api.get_all_towns(use_cache=False)

            if not towns:
                logger.warning("Failed to fetch towns for raid monitoring")
                return

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
