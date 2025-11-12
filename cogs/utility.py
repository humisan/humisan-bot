import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import aiohttp
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Utility(commands.Cog):
    """ユーティリティ機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='serverinfo', description='サーバー情報を表示します')
    async def serverinfo(self, interaction: discord.Interaction):
        """サーバー情報を表示します"""
        # DM チェック
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはギルド内でのみ使用可能です"),
                ephemeral=True
            )
            return

        try:
            guild = interaction.guild
            embed = discord.Embed(
                title=f"サーバー情報 - {guild.name}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.add_field(name="サーバーID", value=guild.id, inline=False)
            embed.add_field(name="所有者", value=guild.owner.mention, inline=False)
            embed.add_field(name="作成日", value=guild.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
            embed.add_field(name="メンバー数", value=guild.member_count, inline=False)
            embed.add_field(name="テキストチャネル数", value=len(guild.text_channels), inline=False)
            embed.add_field(name="ボイスチャネル数", value=len(guild.voice_channels), inline=False)
            embed.add_field(name="ロール数", value=len(guild.roles), inline=False)
            embed.add_field(name="レベル", value=guild.verification_level, inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in serverinfo command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("サーバー情報の取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='avatar', description='ユーザーのアバターを表示します（DMでも使用可）')
    @app_commands.describe(user='アバターを表示するユーザー（省略時は自分）')
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        """ユーザーのアバターを表示します（DM対応）"""
        try:
            if user is None:
                user = interaction.user

            embed = discord.Embed(
                title=f"{user.name} のアバター",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            if user.avatar:
                embed.set_image(url=user.avatar.url)
                embed.add_field(name="URL", value=f"[クリック]({user.avatar.url})", inline=False)
            else:
                embed.description = "このユーザーはアバターを設定していません"

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in avatar command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("アバター取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='roleinfo', description='ロール情報を表示します')
    @app_commands.describe(role='情報を表示するロール')
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        """ロール情報を表示します"""
        # DM チェック
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはギルド内でのみ使用可能です"),
                ephemeral=True
            )
            return

        try:
            embed = discord.Embed(
                title=f"ロール情報 - {role.name}",
                color=role.color,
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(name="ロールID", value=role.id, inline=False)
            embed.add_field(name="色", value=str(role.color), inline=False)
            embed.add_field(name="作成日", value=role.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
            embed.add_field(name="メンバー数", value=len(role.members), inline=False)
            embed.add_field(name="メンション可能", value="はい" if role.mentionable else "いいえ", inline=False)
            embed.add_field(name="管理者権限", value="はい" if role.permissions.administrator else "いいえ", inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in roleinfo command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ロール情報の取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='help', description='ボットのヘルプを表示します')
    async def custom_help(self, interaction: discord.Interaction):
        """ボットのヘルプを表示します"""
        try:
            embed = discord.Embed(
                title="🤖 ボットのコマンド一覧",
                description="すべてのコマンドはスラッシュコマンド（/）で実行します",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            # モデレーション機能
            moderation_commands = [
                "`/kick` - ユーザーをキック",
                "`/ban` - ユーザーをバン",
                "`/unban` - バンを解除",
                "`/timeout` - タイムアウト",
                "`/untimeout` - タイムアウト解除",
                "`/warn` - 警告",
                "`/clear` - メッセージ削除",
                "`/userinfo` - ユーザー情報"
            ]
            embed.add_field(name="🛡️ モデレーション", value="\n".join(moderation_commands), inline=False)

            # 音楽機能
            music_commands = [
                "`/play <URL>` - YouTube URL から曲を再生",
                "`/search <キーワード>` - 曲を検索して再生",
                "`/nowplaying` - 再生中の曲を表示",
                "`/queue` - 再生キューを表示",
                "`/pause` - 一時停止",
                "`/resume` - 再開",
                "`/skip` - スキップ",
                "`/stop` - 停止",
                "`/repeat` - リピートモード変更",
                "`/shuffle` - シャッフル切り替え",
                "`/volume <0-100>` - 音量調整",
                "`/favorite` - 現在の曲をお気に入り登録",
                "`/favorites` - お気に入り一覧表示",
                "`/leave` - ボイスチャネルから退出"
            ]
            embed.add_field(name="🎵 音楽", value="\n".join(music_commands), inline=False)

            # プレイリスト機能
            playlist_commands = [
                "`/playlist create <名前>` - 新規プレイリスト作成",
                "`/playlist add <名前> <URL>` - プレイリストに曲を追加",
                "`/playlist load <名前>` - プレイリストをキューに追加",
                "`/playlist list` - プレイリスト一覧表示"
            ]
            embed.add_field(name="📋 プレイリスト", value="\n".join(playlist_commands), inline=False)

            # エンターテイメント機能
            entertainment_commands = [
                "`/8ball` - 8ボール占い",
                "`/rps` - じゃんけん",
                "`/dice` - サイコロ",
                "`/flip` - コイン投げ",
                "`/joke` - ジョーク",
                "`/choose` - 選択",
                "`/ping` - ピング表示"
            ]
            embed.add_field(name="🎮 エンターテイメント", value="\n".join(entertainment_commands), inline=False)

            # ユーティリティ機能
            utility_commands = [
                "`/serverinfo` - サーバー情報",
                "`/avatar [ユーザー]` - アバター表示（DM対応）",
                "`/roleinfo <ロール>` - ロール情報",
                "`/help` - ヘルプ",
                "`/uptime` - 稼働時間",
                "`/botinfo` - ボット情報",
                "`/suggest <内容>` - 機能提案"
            ]
            embed.add_field(name="🔧 ユーティリティ", value="\n".join(utility_commands), inline=False)

            # その他
            other_commands = [
                "`/mchistory <プレイヤー名>` - Minecraftプレイヤー名履歴"
            ]
            embed.add_field(name="📦 その他", value="\n".join(other_commands), inline=False)

            embed.set_footer(text="各コマンドの詳細は、コマンド入力時に表示されます")

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in help command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ヘルプの取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='uptime', description='ボットの稼働時間を表示します')
    async def uptime(self, interaction: discord.Interaction):
        """ボットの稼働時間を表示します"""
        try:
            uptime_seconds = (datetime.now() - self.bot.start_time).total_seconds()
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)

            embed = discord.Embed(
                title="⏱️ ボットの稼働時間",
                description=f"{hours} 時間 {minutes} 分 {seconds} 秒",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in uptime command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("稼働時間の取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='botinfo', description='ボット情報を表示します')
    async def botinfo(self, interaction: discord.Interaction):
        """ボット情報を表示します"""
        try:
            embed = discord.Embed(
                title="🤖 ボット情報",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.add_field(name="ボット名", value=self.bot.user.name, inline=False)
            embed.add_field(name="ボットID", value=self.bot.user.id, inline=False)
            embed.add_field(name="discord.py バージョン", value=discord.__version__, inline=False)
            embed.add_field(name="サーバー数", value=len(self.bot.guilds), inline=False)
            embed.add_field(name="ユーザー数", value=sum(g.member_count for g in self.bot.guilds), inline=False)
            embed.add_field(name="接続状態", value="✅ 接続中" if self.bot.is_ready() else "❌ 切断中", inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in botinfo command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ボット情報の取得に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='suggest', description='機能を提案します')
    @app_commands.describe(suggestion='提案内容')
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        """機能を提案します"""
        # DM チェック
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはギルド内でのみ使用可能です"),
                ephemeral=True
            )
            return

        try:
            embed = discord.Embed(
                title="💡 提案",
                description=suggestion,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"提案者: {interaction.user.name}")

            # 提案ログチャネルに送信（存在する場合）
            suggest_channel = discord.utils.get(interaction.guild.text_channels, name="suggestions")
            if suggest_channel:
                await suggest_channel.send(embed=embed)

            await interaction.response.send_message(embed=create_success_embed("提案ありがとうございます！", "あなたの提案は記録されました"))
            logger.info(f"{interaction.user.name} suggested: {suggestion}")
        except Exception as e:
            logger.error(f"Error in suggest command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("提案の送信に失敗しました", str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
