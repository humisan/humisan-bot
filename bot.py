import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv
from config import DISCORD_TOKEN, COMMAND_PREFIX
from utils.logger import setup_logger
from utils.database import get_database
from utils.migration import run_migration

# ロガーの設定
logger = setup_logger(__name__)

# 環境変数を読み込む
load_dotenv()

# ボットの初期化
intents = discord.Intents.default()
intents.message_content = True      # メッセージ内容を読み取る
intents.members = True               # メンバー情報（ウェルカム、自動ロール用）
intents.voice_states = True          # 音声状態（音楽機能用）

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.start_time = datetime.now()

# データベース初期化
db = get_database()

# Minecraft API関連の定数
MOJANG_UUID_API = "https://api.mojang.com/users/profiles/minecraft/"
MOJANG_NAME_HISTORY_API = "https://api.mojang.com/user/profiles/"

class MinecraftAPI:
    """Minecraft APIを操作するためのクラス"""

    @staticmethod
    async def get_uuid(username: str) -> dict:
        """
        プレイヤー名からUUIDを取得する

        Args:
            username (str): Minecraftのプレイヤー名

        Returns:
            dict: UUID情報 {'id': uuid, 'name': name}
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(MOJANG_UUID_API + username) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        return None
                    else:
                        return None
            except Exception as e:
                print(f"UUID取得エラー: {e}")
                return None

    @staticmethod
    async def get_name_history(uuid: str) -> list:
        """
        UUIDからプレイヤー名の履歴を取得する

        Args:
            uuid (str): MinecraftのプレイヤーUUID

        Returns:
            list: 名前の履歴リスト
        """
        async with aiohttp.ClientSession() as session:
            try:
                # UUIDのハイフンを削除して送信
                clean_uuid = uuid.replace('-', '')
                url = MOJANG_NAME_HISTORY_API + clean_uuid + "/names"

                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return None
            except Exception as e:
                print(f"名前履歴取得エラー: {e}")
                return None

async def load_cogs():
    """Cogsを読み込む"""
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f'Loaded cog: {filename}')
            except Exception as e:
                logger.error(f'Failed to load cog {filename}: {str(e)}')

@bot.event
async def on_ready():
    """ボットが起動した時のイベント"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready! Currently in {len(bot.guilds)} guilds.')

    # ボットのステータスを設定（常に idle を維持）
    activity = discord.Activity(type=discord.ActivityType.watching, name="/help で コマンド一覧を表示")
    await bot.change_presence(status=discord.Status.idle, activity=activity)
    logger.info("Bot status set to idle (always)")

    try:
        logger.info("Syncing application commands (Global)...")
        synced = await bot.tree.sync()
        logger.info(f"Successfully synced {len(synced)} global application command(s)")

        if synced:
            logger.info("Synced commands:")
            for cmd in synced:
                logger.info(f"  - /{cmd.name}")
        else:
            logger.warning("No commands were synced!")

    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Database migration on first startup
    try:
        logger.info("Running database migration from JSON files...")
        migration_report = run_migration(db)
        if migration_report:
            logger.info("=" * 50)
            logger.info("Database Migration Report:")
            logger.info("=" * 50)
            for key, value in migration_report.items():
                if isinstance(value, dict):
                    logger.info(f"{key}:")
                    for sub_key, sub_value in value.items():
                        logger.info(f"  {sub_key}: {sub_value}")
                else:
                    logger.info(f"{key}: {value}")
            logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Failed to run migration: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    """ボットがギルドに参加した時のイベント"""
    logger.info(f'Joined guild: {guild.name} (ID: {guild.id})')
    # Create server settings in database
    db.create_server_settings(guild.id, guild.name)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    """ボットがギルドから削除された時のイベント"""
    logger.info(f'Left guild: {guild.name} (ID: {guild.id})')

# Status is set to idle in on_ready() and kept as idle (no automatic updates)

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """従来のコマンドエラーハンドリング（互換性のため）"""
    logger.error(f'Error in command {ctx.command}: {str(error)}')
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ エラー",
            description=f"引数が足りません\n使用方法: `{COMMAND_PREFIX}{ctx.command} {ctx.command.signature}`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ エラー",
            description="このコマンドを実行する権限がありません",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        pass  # コマンドが見つからない場合は何もしない
    else:
        embed = discord.Embed(
            title="❌ エラー",
            description=f"コマンド実行中にエラーが発生しました: {str(error)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """アプリケーションコマンドのエラーハンドリング"""
    logger.error(f'Error in app command: {str(error)}')

    if isinstance(error, discord.app_commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ エラー",
            description="このコマンドを実行する権限がありません",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="❌ エラー",
            description=f"このコマンドはクールダウン中です。{error.retry_after:.2f}秒後に再試行してください",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ エラー",
            description=f"コマンド実行中にエラーが発生しました: {str(error)}",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

# ボットの実行
async def main():
    """ボット起動関数"""
    async with bot:
        await load_cogs()
        try:
            await bot.start(DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"ボット起動エラー: {str(e)}")
            raise

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("エラー: DISCORD_TOKEN が環境変数に設定されていません")
        print(".env ファイルを作成し、DISCORD_TOKEN を設定してください")
        exit(1)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ボットがシャットダウンしました")
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {str(e)}")
