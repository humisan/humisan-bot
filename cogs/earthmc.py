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

# EarthMC API configuration
EARTHMC_API_BASE = "https://api.earthmc.net/v3/aurora"
EARTHMC_SERVER_ENDPOINT = f"{EARTHMC_API_BASE}/server"
EARTHMC_TOWNS_ENDPOINT = f"{EARTHMC_API_BASE}/towns"
EARTHMC_NATIONS_ENDPOINT = f"{EARTHMC_API_BASE}/nations"
EARTHMC_PLAYERS_ENDPOINT = f"{EARTHMC_API_BASE}/players"

VOTEPARTY_CHECK_INTERVAL = 1800  # 30 minutes in seconds


class EarthMCAPI:
    """EarthMC API wrapper for retrieving game information"""

    def __init__(self):
        self.base_url = EARTHMC_API_BASE
        self.timeout = aiohttp.ClientTimeout(total=10)
        self._cache = {}
        self._cache_time = {}

    async def get_server_status(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get server status including VoteParty information

        Args:
            use_cache: Whether to use cached data

        Returns:
            Dictionary with server info or None if error
        """
        if use_cache and self._is_cache_valid('server'):
            logger.debug("Using cached server data")
            return self._cache.get('server')

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(EARTHMC_SERVER_ENDPOINT) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache['server'] = data
                        self._cache_time['server'] = datetime.now()
                        logger.info("Successfully fetched server status")
                        return data
                    else:
                        logger.error(f"EarthMC API returned status {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error("Timeout while fetching server status")
            return None
        except Exception as e:
            logger.error(f"Error fetching server status: {e}")
            return None

    async def get_town(self, town_name: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get town information

        Args:
            town_name: Name of the town
            use_cache: Whether to use cached data

        Returns:
            Dictionary with town info or None if not found
        """
        cache_key = f"town:{town_name}"

        if use_cache and self._is_cache_valid(cache_key):
            logger.debug(f"Using cached town data for {town_name}")
            return self._cache.get(cache_key)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(EARTHMC_TOWNS_ENDPOINT, json={"name": town_name}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache[cache_key] = data
                        self._cache_time[cache_key] = datetime.now()
                        logger.info(f"Successfully fetched town data for {town_name}")
                        return data
                    elif response.status == 404:
                        logger.warning(f"Town '{town_name}' not found")
                        return None
                    else:
                        logger.error(f"Error fetching town {town_name}: {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching town {town_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching town {town_name}: {e}")
            return None

    async def get_nation(self, nation_name: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get nation information

        Args:
            nation_name: Name of the nation
            use_cache: Whether to use cached data

        Returns:
            Dictionary with nation info or None if not found
        """
        cache_key = f"nation:{nation_name}"

        if use_cache and self._is_cache_valid(cache_key):
            logger.debug(f"Using cached nation data for {nation_name}")
            return self._cache.get(cache_key)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(EARTHMC_NATIONS_ENDPOINT, json={"name": nation_name}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache[cache_key] = data
                        self._cache_time[cache_key] = datetime.now()
                        logger.info(f"Successfully fetched nation data for {nation_name}")
                        return data
                    elif response.status == 404:
                        logger.warning(f"Nation '{nation_name}' not found")
                        return None
                    else:
                        logger.error(f"Error fetching nation {nation_name}: {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching nation {nation_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching nation {nation_name}: {e}")
            return None

    async def get_player_residence(self, player_name: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get player residence information

        Args:
            player_name: Name of the player
            use_cache: Whether to use cached data

        Returns:
            Dictionary with player info or None if not found
        """
        cache_key = f"player:{player_name}"

        if use_cache and self._is_cache_valid(cache_key):
            logger.debug(f"Using cached player data for {player_name}")
            return self._cache.get(cache_key)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(EARTHMC_PLAYERS_ENDPOINT, json={"name": player_name}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache[cache_key] = data
                        self._cache_time[cache_key] = datetime.now()
                        logger.info(f"Successfully fetched player data for {player_name}")
                        return data
                    elif response.status == 404:
                        logger.warning(f"Player '{player_name}' not found")
                        return None
                    else:
                        logger.error(f"Error fetching player {player_name}: {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching player {player_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching player {player_name}: {e}")
            return None

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


class EarthMCCog(commands.Cog):
    """EarthMC information commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = EarthMCAPI()
        self.db = None

        # Start the VoteParty monitoring task
        self.monitor_voteparty.start()

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monitor_voteparty.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize database when bot is ready"""
        if self.db is None:
            from utils.database import get_database
            self.db = get_database()
        logger.info("EarthMC cog is ready")

    # ==================== SLASH COMMANDS ====================

    earthmc_group = app_commands.Group(name="earthmc", description="EarthMCサーバーの情報を確認")

    @earthmc_group.command(name="town", description="タウン情報を表示")
    @app_commands.describe(name="タウン名")
    async def earthmc_town(self, interaction: discord.Interaction, name: str):
        """Display town information"""
        await interaction.response.defer()

        try:
            logger.info(f"Town info requested for {name} by {interaction.user}")

            town_data = await self.api.get_town(name)

            if not town_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "タウンが見つかりません",
                        f"'{name}'という名前のタウンが見つかりませんでした。\n"
                        f"スペルを確認して再度試してください。"
                    ),
                    ephemeral=True
                )
                return

            # Create town embed
            embed = discord.Embed(
                title=f"🏛️ {town_data.get('name', name)}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            # Mayor
            if 'mayor' in town_data:
                embed.add_field(name="市長", value=f"👤 {town_data['mayor']}", inline=True)

            # Nation
            if 'nation' in town_data:
                embed.add_field(name="国家", value=f"🏰 {town_data['nation']}", inline=True)

            # Residents
            if 'residents' in town_data:
                residents = town_data['residents']
                if isinstance(residents, list):
                    resident_count = len(residents)
                else:
                    resident_count = residents
                embed.add_field(name="住民数", value=f"👥 {resident_count}", inline=True)

            # Area
            if 'area' in town_data:
                embed.add_field(name="面積", value=f"📏 {town_data['area']} ブロック", inline=True)

            # Founded
            if 'founded' in town_data:
                embed.add_field(name="建設日", value=town_data['founded'], inline=True)

            # Public/Private
            if 'public' in town_data:
                public_status = "🔓 公開" if town_data['public'] else "🔒 非公開"
                embed.add_field(name="ステータス", value=public_status, inline=True)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc town command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @earthmc_group.command(name="nation", description="国家情報を表示")
    @app_commands.describe(name="国家名")
    async def earthmc_nation(self, interaction: discord.Interaction, name: str):
        """Display nation information"""
        await interaction.response.defer()

        try:
            logger.info(f"Nation info requested for {name} by {interaction.user}")

            nation_data = await self.api.get_nation(name)

            if not nation_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "国家が見つかりません",
                        f"'{name}'という名前の国家が見つかりませんでした。\n"
                        f"スペルを確認して再度試してください。"
                    ),
                    ephemeral=True
                )
                return

            # Create nation embed
            embed = discord.Embed(
                title=f"🏰 {nation_data.get('name', name)}",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )

            # King
            if 'king' in nation_data:
                embed.add_field(name="国王", value=f"👑 {nation_data['king']}", inline=True)

            # Capital
            if 'capital' in nation_data:
                embed.add_field(name="首都", value=f"🏛️ {nation_data['capital']}", inline=True)

            # Residents
            if 'residents' in nation_data:
                residents = nation_data['residents']
                if isinstance(residents, list):
                    resident_count = len(residents)
                else:
                    resident_count = residents
                embed.add_field(name="国民数", value=f"👥 {resident_count}", inline=True)

            # Towns
            if 'towns' in nation_data:
                towns = nation_data['towns']
                town_count = len(towns) if isinstance(towns, list) else towns
                embed.add_field(name="タウン数", value=f"🏘️ {town_count}", inline=True)

            # Area
            if 'area' in nation_data:
                embed.add_field(name="面積", value=f"📏 {nation_data['area']} ブロック", inline=True)

            # Founded
            if 'founded' in nation_data:
                embed.add_field(name="建国日", value=nation_data['founded'], inline=True)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc nation command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @earthmc_group.command(name="res", description="プレイヤー/レジデンス情報を表示")
    @app_commands.describe(name="プレイヤー名")
    async def earthmc_residence(self, interaction: discord.Interaction, name: str):
        """Display player residence information"""
        await interaction.response.defer()

        try:
            logger.info(f"Player info requested for {name} by {interaction.user}")

            player_data = await self.api.get_player_residence(name)

            if not player_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "プレイヤーが見つかりません",
                        f"'{name}'というプレイヤーが見つかりませんでした。\n"
                        f"スペルを確認して再度試してください。"
                    ),
                    ephemeral=True
                )
                return

            # Create player embed
            embed = discord.Embed(
                title=f"👤 {player_data.get('name', name)}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            # Town
            if 'town' in player_data:
                embed.add_field(name="所属タウン", value=f"🏛️ {player_data['town']}", inline=True)

            # Nation
            if 'nation' in player_data:
                embed.add_field(name="所属国家", value=f"🏰 {player_data['nation']}", inline=True)

            # Rank
            if 'rank' in player_data:
                embed.add_field(name="身分", value=f"⭐ {player_data['rank']}", inline=True)

            # Balance
            if 'balance' in player_data:
                embed.add_field(name="資金", value=f"💰 ${player_data['balance']}", inline=True)

            # Last Seen
            if 'lastOnline' in player_data:
                embed.add_field(name="最後にオンライン", value=player_data['lastOnline'], inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc residence command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @earthmc_group.command(name="voteparty", description="投票パーティーの情報を表示")
    async def earthmc_voteparty(self, interaction: discord.Interaction):
        """Display VoteParty information"""
        await interaction.response.defer()

        try:
            logger.info(f"VoteParty info requested by {interaction.user}")

            server_data = await self.api.get_server_status(use_cache=False)

            if not server_data or 'voteParty' not in server_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "情報取得失敗",
                        "投票パーティーの情報を取得できませんでした。後でもう一度試してください。"
                    ),
                    ephemeral=True
                )
                return

            vote_party = server_data['voteParty']

            # Create VoteParty embed
            embed = discord.Embed(
                title="🗳️ 投票パーティー",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            if 'currentVotes' in vote_party and 'targetVotes' in vote_party:
                current = vote_party['currentVotes']
                target = vote_party['targetVotes']
                progress = (current / target * 100) if target > 0 else 0

                embed.add_field(
                    name="投票進捗",
                    value=f"{current}/{target} ({progress:.1f}%)",
                    inline=False
                )

                # Progress bar
                bar_length = 20
                filled = int(bar_length * current / target) if target > 0 else 0
                bar = "█" * filled + "░" * (bar_length - filled)
                embed.add_field(
                    name="進捗バー",
                    value=f"`{bar}`",
                    inline=False
                )

            if 'reward' in vote_party:
                embed.add_field(
                    name="報酬",
                    value=f"🎁 {vote_party['reward']}",
                    inline=False
                )

            embed.set_footer(text="EarthMC Aurora サーバー | 次の更新: 投票パーティー達成時")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc voteparty command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    voteparty_group = app_commands.Group(name="voteparty-notify", description="投票パーティー通知を管理")

    @voteparty_group.command(name="enable", description="このチャネルで30分ごとの投票パーティー通知を有効化")
    @app_commands.describe(channel="通知を送信するチャネル")
    async def voteparty_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Enable VoteParty notifications"""
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

            if self.db.setup_earthmc_voteparty_notifications(guild_id, channel_id):
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "通知を有効化しました",
                        f"投票パーティーの通知が30分ごとに {channel.mention} に送信されます。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("有効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error enabling VoteParty notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @voteparty_group.command(name="disable", description="投票パーティー通知を無効化")
    async def voteparty_disable(self, interaction: discord.Interaction):
        """Disable VoteParty notifications"""
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

            if self.db.disable_earthmc_voteparty_notifications(guild_id):
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "通知を無効化しました",
                        "このサーバーでの投票パーティー通知が停止されました。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("無効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error disabling VoteParty notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    # ==================== MONITORING TASK ====================

    @tasks.loop(seconds=VOTEPARTY_CHECK_INTERVAL)
    async def monitor_voteparty(self):
        """Periodically check and notify about VoteParty status"""
        if self.db is None:
            return

        try:
            # Get server status
            server_data = await self.api.get_server_status(use_cache=False)

            if not server_data or 'voteParty' not in server_data:
                logger.warning("Failed to fetch VoteParty data")
                return

            vote_party = server_data['voteParty']

            # Get all active notification channels
            notification_channels = self.db.get_all_earthmc_voteparty_notifications()

            for config in notification_channels:
                try:
                    channel_id = int(config['channel_id'])
                    guild_id = config['guild_id']

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
                        continue

                    # Create and send notification
                    await self._send_voteparty_notification(channel, vote_party)

                    # Update notification time
                    self.db.update_earthmc_voteparty_notification_time(guild_id)

                except Exception as e:
                    logger.error(f"Error sending VoteParty notification: {e}")

        except Exception as e:
            logger.error(f"Error in monitor_voteparty task: {e}")

    @monitor_voteparty.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready before starting monitoring"""
        await self.bot.wait_until_ready()
        logger.info("EarthMC VoteParty monitoring task started")

    async def _send_voteparty_notification(self, channel: discord.TextChannel, vote_party: Dict[str, Any]):
        """Send VoteParty notification to a channel"""
        try:
            embed = discord.Embed(
                title="🗳️ 投票パーティー進捗",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            if 'currentVotes' in vote_party and 'targetVotes' in vote_party:
                current = vote_party['currentVotes']
                target = vote_party['targetVotes']
                progress = (current / target * 100) if target > 0 else 0

                embed.add_field(
                    name="投票数",
                    value=f"{current}/{target} ({progress:.1f}%)",
                    inline=False
                )

                # Progress bar
                bar_length = 20
                filled = int(bar_length * current / target) if target > 0 else 0
                bar = "█" * filled + "░" * (bar_length - filled)
                embed.add_field(
                    name="進捗",
                    value=f"`{bar}`",
                    inline=False
                )

            if 'reward' in vote_party:
                embed.add_field(
                    name="報酬",
                    value=f"🎁 {vote_party['reward']}",
                    inline=False
                )

            embed.set_footer(text="EarthMC Aurora サーバー")

            await channel.send(embed=embed)
            logger.info(f"VoteParty notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending VoteParty notification: {e}")


async def setup(bot: commands.Bot):
    """Load the EarthMC cog"""
    # Create a temporary instance to register command groups
    cog = EarthMCCog(bot)

    # Add the main command group
    bot.tree.add_command(cog.earthmc_group)
    # Add the voteparty notify subgroup to the main group
    cog.earthmc_group.add_command(cog.voteparty_group)

    await bot.add_cog(cog)
    logger.info("EarthMC cog loaded successfully")
