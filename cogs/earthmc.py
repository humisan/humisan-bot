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


def format_timestamp(timestamp) -> str:
    """Convert Unix timestamp (milliseconds or seconds) to readable format"""
    try:
        # Handle both milliseconds and seconds
        if isinstance(timestamp, (int, float)):
            # If timestamp is very large, it's likely in milliseconds
            if timestamp > 10000000000:
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y年%m月%d日 %H:%M:%S")
        else:
            # String timestamp, return as is
            return str(timestamp)
    except Exception as e:
        logger.warning(f"Failed to convert timestamp {timestamp}: {e}")
        return str(timestamp)

# EarthMC API configuration
EARTHMC_API_BASE = "https://api.earthmc.net/v3/aurora"
EARTHMC_SERVER_ENDPOINT = f"{EARTHMC_API_BASE}/"
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
                async with session.post(EARTHMC_TOWNS_ENDPOINT, json={"query": [town_name]}) as response:
                    if response.status == 200:
                        data = await response.json()
                        # API returns an array of matches, take the first result
                        if isinstance(data, list) and len(data) > 0:
                            town_info = data[0]
                            self._cache[cache_key] = town_info
                            self._cache_time[cache_key] = datetime.now()
                            logger.info(f"Successfully fetched town data for {town_name}")
                            return town_info
                        else:
                            logger.warning(f"Town '{town_name}' not found")
                            return None
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
                async with session.post(EARTHMC_NATIONS_ENDPOINT, json={"query": [nation_name]}) as response:
                    if response.status == 200:
                        data = await response.json()
                        # API returns an array of matches, take the first result
                        if isinstance(data, list) and len(data) > 0:
                            nation_info = data[0]
                            self._cache[cache_key] = nation_info
                            self._cache_time[cache_key] = datetime.now()
                            logger.info(f"Successfully fetched nation data for {nation_name}")
                            return nation_info
                        else:
                            logger.warning(f"Nation '{nation_name}' not found")
                            return None
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
                async with session.post(EARTHMC_PLAYERS_ENDPOINT, json={"query": [player_name]}) as response:
                    if response.status == 200:
                        data = await response.json()
                        # API returns an array of matches, take the first result
                        if isinstance(data, list) and len(data) > 0:
                            player_info = data[0]
                            self._cache[cache_key] = player_info
                            self._cache_time[cache_key] = datetime.now()
                            logger.info(f"Successfully fetched player data for {player_name}")
                            return player_info
                        else:
                            logger.warning(f"Player '{player_name}' not found")
                            return None
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

    @app_commands.command(name="town", description="タウン情報を表示")
    @app_commands.describe(name="タウン名")
    async def town(self, interaction: discord.Interaction, name: str):
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

            # UUID
            if 'uuid' in town_data:
                embed.add_field(name="UUID", value=f"`{town_data['uuid']}`", inline=True)

            # Mayor
            if 'mayor' in town_data:
                mayor = town_data['mayor']
                if isinstance(mayor, dict):
                    embed.add_field(name="市長", value=f"👤 **{mayor.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="市長", value=f"👤 **{mayor}**", inline=True)

            # Founder
            if 'founder' in town_data:
                embed.add_field(name="創設者", value=f"🏗️ **{town_data['founder']}**", inline=True)

            # Nation
            if 'nation' in town_data and town_data['nation']:
                nation = town_data['nation']
                if isinstance(nation, dict):
                    embed.add_field(name="国家", value=f"🏰 **{nation.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="国家", value=f"🏰 **{nation}**", inline=True)

            # Status fields
            if 'status' in town_data:
                status = town_data['status']
                status_str = ""
                if status.get('isPublic'):
                    status_str += "🔓 **公開** | "
                else:
                    status_str += "🔒 **非公開** | "
                if status.get('isOpen'):
                    status_str += "✅ **参加可能** | "
                else:
                    status_str += "❌ **参加不可** | "
                if status.get('isCapital'):
                    status_str += "👑 **首都**"
                if status.get('isRuined'):
                    status_str += "💔 **廃墟**"
                if status_str:
                    embed.add_field(name="ステータス", value=status_str.rstrip(" | "), inline=False)

            # Timestamps
            if 'timestamps' in town_data:
                timestamps = town_data['timestamps']
                if timestamps.get('registered'):
                    embed.add_field(name="建設日", value=f"`{format_timestamp(timestamps['registered'])}`", inline=True)
                if timestamps.get('joinedNationAt'):
                    embed.add_field(name="国家参加日", value=f"`{format_timestamp(timestamps['joinedNationAt'])}`", inline=True)

            # Stats
            if 'stats' in town_data:
                stats = town_data['stats']
                stats_text = ""
                if 'numResidents' in stats:
                    stats_text += f"👥 **住民数:** `{stats['numResidents']}`\n"
                if 'numTownBlocks' in stats:
                    max_blocks = stats.get('maxTownBlocks', 'Unknown')
                    stats_text += f"📦 **タウンブロック:** `{stats['numTownBlocks']}/{max_blocks}`\n"
                if 'numTrusted' in stats:
                    stats_text += f"🤝 **信頼メンバー:** `{stats['numTrusted']}`\n"
                if 'numOutlaws' in stats:
                    stats_text += f"⚠️ **アウトロー:** `{stats['numOutlaws']}`\n"
                if 'balance' in stats:
                    stats_text += f"💰 **資金:** `{stats['balance']} G`\n"
                if 'forSalePrice' in stats and stats['forSalePrice']:
                    stats_text += f"💵 **販売価格:** `{stats['forSalePrice']} G`"
                if stats_text:
                    embed.add_field(name="**統計情報**", value=stats_text.rstrip("\n"), inline=False)

            # Board
            if 'board' in town_data and town_data['board']:
                embed.add_field(name="📰 **お知らせ**", value=f"```\n{town_data['board'][:1024]}\n```", inline=False)

            # Wiki
            if 'wiki' in town_data and town_data['wiki']:
                embed.add_field(name="📖 **Wiki**", value=f"[リンク]({town_data['wiki']})", inline=False)

            # Residents list - split into multiple fields if needed
            if 'residents' in town_data:
                residents = town_data['residents']
                if isinstance(residents, list) and residents:
                    resident_names = [r.get('name', 'Unknown') if isinstance(r, dict) else r for r in residents]
                    # Split into chunks of ~50 names per field to avoid character limit
                    chunk_size = 50
                    for i in range(0, len(resident_names), chunk_size):
                        chunk = resident_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"👥 **住民** ({i+1}-{min(i+chunk_size, len(resident_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            # Trusted list - split into multiple fields if needed
            if 'trusted' in town_data:
                trusted = town_data['trusted']
                if isinstance(trusted, list) and trusted:
                    trusted_names = [t.get('name', 'Unknown') if isinstance(t, dict) else t for t in trusted]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(trusted_names), chunk_size):
                        chunk = trusted_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"🤝 **信頼メンバー** ({i+1}-{min(i+chunk_size, len(trusted_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            # Outlaws list - split into multiple fields if needed
            if 'outlaws' in town_data:
                outlaws = town_data['outlaws']
                if isinstance(outlaws, list) and outlaws:
                    outlaw_names = [o.get('name', 'Unknown') if isinstance(o, dict) else o for o in outlaws]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(outlaw_names), chunk_size):
                        chunk = outlaw_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"⚠️ **アウトロー** ({i+1}-{min(i+chunk_size, len(outlaw_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc town command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="nation", description="国家情報を表示")
    @app_commands.describe(name="国家名")
    async def nation(self, interaction: discord.Interaction, name: str):
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

            # UUID
            if 'uuid' in nation_data:
                embed.add_field(name="UUID", value=f"`{nation_data['uuid']}`", inline=True)

            # King
            if 'king' in nation_data:
                king = nation_data['king']
                if isinstance(king, dict):
                    embed.add_field(name="国王", value=f"👑 **{king.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="国王", value=f"👑 **{king}**", inline=True)

            # Capital
            if 'capital' in nation_data:
                capital = nation_data['capital']
                if isinstance(capital, dict):
                    embed.add_field(name="首都", value=f"🏛️ **{capital.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="首都", value=f"🏛️ **{capital}**", inline=True)

            # Status fields
            if 'status' in nation_data:
                status = nation_data['status']
                status_str = ""
                if status.get('isPublic'):
                    status_str += "🔓 **公開** | "
                else:
                    status_str += "🔒 **非公開** | "
                if status.get('isOpen'):
                    status_str += "✅ **参加可能**"
                else:
                    status_str += "❌ **参加不可**"
                if status_str:
                    embed.add_field(name="ステータス", value=status_str.rstrip(" | "), inline=False)

            # Timestamps
            if 'timestamps' in nation_data:
                timestamps = nation_data['timestamps']
                if timestamps.get('registered'):
                    embed.add_field(name="建国日", value=f"`{format_timestamp(timestamps['registered'])}`", inline=True)

            # Stats
            if 'stats' in nation_data:
                stats = nation_data['stats']
                stats_text = ""
                if 'numResidents' in stats:
                    stats_text += f"👥 **国民数:** `{stats['numResidents']}`\n"
                if 'numTowns' in stats:
                    stats_text += f"🏘️ **タウン数:** `{stats['numTowns']}`\n"
                if 'numTownBlocks' in stats:
                    stats_text += f"📦 **タウンブロック数:** `{stats['numTownBlocks']}`\n"
                if 'numAllies' in stats:
                    stats_text += f"🤝 **同盟国:** `{stats['numAllies']}`\n"
                if 'numEnemies' in stats:
                    stats_text += f"⚔️ **敵国:** `{stats['numEnemies']}`\n"
                if 'balance' in stats:
                    stats_text += f"💰 **資金:** `{stats['balance']} G`"
                if stats_text:
                    embed.add_field(name="**統計情報**", value=stats_text.rstrip("\n"), inline=False)

            # Board
            if 'board' in nation_data and nation_data['board']:
                embed.add_field(name="📰 **お知らせ**", value=f"```\n{nation_data['board'][:1024]}\n```", inline=False)

            # Wiki
            if 'wiki' in nation_data and nation_data['wiki']:
                embed.add_field(name="📖 **Wiki**", value=f"[リンク]({nation_data['wiki']})", inline=False)

            # Residents list - split into multiple fields if needed
            if 'residents' in nation_data:
                residents = nation_data['residents']
                if isinstance(residents, list) and residents:
                    resident_names = [r.get('name', 'Unknown') if isinstance(r, dict) else r for r in residents]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(resident_names), chunk_size):
                        chunk = resident_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"👥 **国民** ({i+1}-{min(i+chunk_size, len(resident_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            # Towns list - split into multiple fields if needed
            if 'towns' in nation_data:
                towns = nation_data['towns']
                if isinstance(towns, list) and towns:
                    town_names = [t.get('name', 'Unknown') if isinstance(t, dict) else t for t in towns]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(town_names), chunk_size):
                        chunk = town_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"🏘️ **タウン** ({i+1}-{min(i+chunk_size, len(town_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            # Allies list - split into multiple fields if needed
            if 'allies' in nation_data:
                allies = nation_data['allies']
                if isinstance(allies, list) and allies:
                    ally_names = [a.get('name', 'Unknown') if isinstance(a, dict) else a for a in allies]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(ally_names), chunk_size):
                        chunk = ally_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"🤝 **同盟国** ({i+1}-{min(i+chunk_size, len(ally_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            # Enemies list - split into multiple fields if needed
            if 'enemies' in nation_data:
                enemies = nation_data['enemies']
                if isinstance(enemies, list) and enemies:
                    enemy_names = [e.get('name', 'Unknown') if isinstance(e, dict) else e for e in enemies]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(enemy_names), chunk_size):
                        chunk = enemy_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"⚔️ **敵国** ({i+1}-{min(i+chunk_size, len(enemy_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc nation command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="resident", description="プレイヤー情報を表示")
    @app_commands.describe(name="プレイヤー名")
    async def resident(self, interaction: discord.Interaction, name: str):
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
                title=f"👤 {player_data.get('formattedName', player_data.get('name', name))}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            # UUID
            if 'uuid' in player_data:
                embed.add_field(name="UUID", value=f"`{player_data['uuid']}`", inline=True)

            # Title and Surname
            if 'title' in player_data and player_data['title']:
                embed.add_field(name="タイトル", value=f"**{player_data['title']}**", inline=True)
            if 'surname' in player_data and player_data['surname']:
                embed.add_field(name="姓氏", value=f"**{player_data['surname']}**", inline=True)

            # About
            if 'about' in player_data and player_data['about']:
                embed.add_field(name="📝 **自己紹介**", value=f"```\n{player_data['about'][:1024]}\n```", inline=False)

            # Status
            if 'status' in player_data:
                status = player_data['status']
                status_str = ""
                if status.get('isOnline'):
                    status_str += "🟢 **オンライン**"
                else:
                    status_str += "⚫ **オフライン**"
                if status.get('isNPC'):
                    status_str += " | 🤖 **NPC**"
                if status.get('isMayor'):
                    status_str += " | 🏛️ **市長**"
                if status.get('isKing'):
                    status_str += " | 👑 **国王**"
                if status_str:
                    embed.add_field(name="ステータス", value=status_str, inline=False)

            # Town
            if 'town' in player_data and player_data['town']:
                town = player_data['town']
                if isinstance(town, dict):
                    embed.add_field(name="所属タウン", value=f"🏛️ **{town.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="所属タウン", value=f"🏛️ **{town}**", inline=True)

            # Nation
            if 'nation' in player_data and player_data['nation']:
                nation = player_data['nation']
                if isinstance(nation, dict):
                    embed.add_field(name="所属国家", value=f"🏰 **{nation.get('name', 'Unknown')}**", inline=True)
                else:
                    embed.add_field(name="所属国家", value=f"🏰 **{nation}**", inline=True)

            # Timestamps
            if 'timestamps' in player_data:
                timestamps = player_data['timestamps']
                dates_text = ""
                if timestamps.get('registered'):
                    dates_text += f"📅 **作成日:** `{format_timestamp(timestamps['registered'])}`\n"
                if timestamps.get('joinedTownAt'):
                    dates_text += f"🏘️ **参加日:** `{format_timestamp(timestamps['joinedTownAt'])}`\n"
                if timestamps.get('lastOnline'):
                    dates_text += f"⏰ **最終ログイン:** `{format_timestamp(timestamps['lastOnline'])}`"
                if dates_text:
                    embed.add_field(name="**日付情報**", value=dates_text.rstrip("\n"), inline=False)

            # Stats
            if 'stats' in player_data:
                stats = player_data['stats']
                stats_text = ""
                if 'balance' in stats:
                    stats_text += f"💰 **所持金:** `{stats['balance']} G`\n"
                if 'numFriends' in stats:
                    stats_text += f"🤝 **フレンド数:** `{stats['numFriends']}`"
                if stats_text:
                    embed.add_field(name="**統計情報**", value=stats_text.rstrip("\n"), inline=False)

            # Ranks
            if 'ranks' in player_data:
                ranks = player_data['ranks']
                rank_text = ""
                if isinstance(ranks, dict):
                    if 'townRanks' in ranks and ranks['townRanks']:
                        town_ranks = ranks['townRanks']
                        if isinstance(town_ranks, list):
                            rank_text += f"🏛️ **タウンランク:** `{', '.join(town_ranks)}`"
                    if 'nationRanks' in ranks and ranks['nationRanks']:
                        nation_ranks = ranks['nationRanks']
                        if isinstance(nation_ranks, list):
                            if rank_text:
                                rank_text += "\n"
                            rank_text += f"🏰 **国家ランク:** `{', '.join(nation_ranks)}`"
                elif isinstance(ranks, list) and ranks:
                    rank_text = f"`{', '.join(ranks)}`"

                if rank_text:
                    embed.add_field(name="**ランク**", value=rank_text, inline=False)

            # Friends list - split into multiple fields if needed
            if 'friends' in player_data:
                friends = player_data['friends']
                if isinstance(friends, list) and friends:
                    friend_names = [f.get('name', 'Unknown') if isinstance(f, dict) else f for f in friends]
                    # Split into chunks
                    chunk_size = 50
                    for i in range(0, len(friend_names), chunk_size):
                        chunk = friend_names[i:i+chunk_size]
                        chunk_text = "`, `".join(chunk)
                        field_name = f"👥 **フレンド** ({i+1}-{min(i+chunk_size, len(friend_names))})"
                        embed.add_field(name=field_name, value=f"`{chunk_text}`", inline=False)

            embed.set_footer(text="EarthMC Aurora サーバー")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc residence command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="voteparty", description="Vote Party の情報を表示")
    async def voteparty(self, interaction: discord.Interaction):
        """Display Vote Party information"""
        await interaction.response.defer()

        try:
            logger.info(f"Vote Party info requested by {interaction.user}")

            server_data = await self.api.get_server_status(use_cache=False)

            if not server_data or 'voteParty' not in server_data:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "情報取得失敗",
                        "Vote Party の情報を取得できませんでした。後でもう一度試してください。"
                    ),
                    ephemeral=True
                )
                return

            vote_party = server_data['voteParty']

            # Create Vote Party embed
            embed = discord.Embed(
                title="🗳️ Vote Party",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            if 'currentVotes' in vote_party and 'targetVotes' in vote_party:
                current = vote_party['currentVotes']
                target = vote_party['targetVotes']
                progress = (current / target * 100) if target > 0 else 0

                embed.add_field(
                    name="**投票進捗**",
                    value=f"`{current}` / `{target}` (**{progress:.1f}%**)",
                    inline=False
                )

                # Progress bar
                bar_length = 20
                filled = int(bar_length * current / target) if target > 0 else 0
                bar = "█" * filled + "░" * (bar_length - filled)
                embed.add_field(
                    name="**進捗バー**",
                    value=f"```\n{bar}\n```",
                    inline=False
                )

            if 'reward' in vote_party:
                embed.add_field(
                    name="**報酬**",
                    value=f"🎁 **{vote_party['reward']}**",
                    inline=False
                )

            embed.set_footer(text="EarthMC Aurora サーバー | 次の更新: Vote Party 達成時")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in earthmc voteparty command: {e}")
            await interaction.followup.send(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="voteparty-enable", description="30分ごとの Vote Party 通知を有効化")
    @app_commands.describe(channel="通知を送信するチャネル")
    async def voteparty_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Enable Vote Party notifications"""
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
                        f"Vote Party の通知が30分ごとに {channel.mention} に送信されます。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("有効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error enabling Vote Party notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    @app_commands.command(name="voteparty-disable", description="Vote Party 通知を無効化")
    async def voteparty_disable(self, interaction: discord.Interaction):
        """Disable Vote Party notifications"""
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
                        "このサーバーでの Vote Party 通知が停止されました。"
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("無効化に失敗しました", "後でもう一度試してください。"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error disabling Vote Party notifications: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    # ==================== MONITORING TASK ====================

    @tasks.loop(seconds=VOTEPARTY_CHECK_INTERVAL)
    async def monitor_voteparty(self):
        """Periodically check and notify about Vote Party status"""
        if self.db is None:
            return

        try:
            # Get server status
            server_data = await self.api.get_server_status(use_cache=False)

            if not server_data or 'voteParty' not in server_data:
                logger.warning("Failed to fetch Vote Party data")
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
                    logger.error(f"Error sending Vote Party notification: {e}")

        except Exception as e:
            logger.error(f"Error in monitor_voteparty task: {e}")

    @monitor_voteparty.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready before starting monitoring"""
        await self.bot.wait_until_ready()
        logger.info("EarthMC Vote Party monitoring task started")

    async def _send_voteparty_notification(self, channel: discord.TextChannel, vote_party: Dict[str, Any]):
        """Send Vote Party notification to a channel"""
        try:
            embed = discord.Embed(
                title="🗳️ Vote Party 進捗",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            if 'currentVotes' in vote_party and 'targetVotes' in vote_party:
                current = vote_party['currentVotes']
                target = vote_party['targetVotes']
                progress = (current / target * 100) if target > 0 else 0

                embed.add_field(
                    name="**投票数**",
                    value=f"`{current}` / `{target}` (**{progress:.1f}%**)",
                    inline=False
                )

                # Progress bar
                bar_length = 20
                filled = int(bar_length * current / target) if target > 0 else 0
                bar = "█" * filled + "░" * (bar_length - filled)
                embed.add_field(
                    name="**進捗**",
                    value=f"```\n{bar}\n```",
                    inline=False
                )

            if 'reward' in vote_party:
                embed.add_field(
                    name="**報酬**",
                    value=f"🎁 **{vote_party['reward']}**",
                    inline=False
                )

            embed.set_footer(text="EarthMC Aurora サーバー")

            await channel.send(embed=embed)
            logger.info(f"Vote Party notification sent to channel {channel.id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send message to channel {channel.id}")
        except Exception as e:
            logger.error(f"Error sending Vote Party notification: {e}")


async def setup(bot: commands.Bot):
    """Load the EarthMC cog"""
    cog = EarthMCCog(bot)
    await bot.add_cog(cog)
    logger.info("EarthMC cog loaded successfully")
