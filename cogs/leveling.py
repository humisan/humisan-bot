import discord
from discord.ext import commands
from discord import app_commands
from utils.database import Database
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
import random
import time
from typing import Dict

logger = setup_logger(__name__)

class Leveling(commands.Cog):
    """レベル・経験値システム"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.cooldowns: Dict[str, float] = {}  # ユーザーIDとタイムスタンプ

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """メッセージ送信時にXPを付与"""
        # ボット自身のメッセージは無視
        if message.author.bot:
            return

        # DMは無視
        if not message.guild:
            return

        # クールダウンチェック（60秒）
        user_key = f"{message.guild.id}_{message.author.id}"
        current_time = time.time()

        if user_key in self.cooldowns:
            if current_time - self.cooldowns[user_key] < 60:
                return

        self.cooldowns[user_key] = current_time

        # ランダムなXPを付与（15-25）
        xp_gain = random.randint(15, 25)
        level, xp, leveled_up = self.db.add_xp(
            str(message.guild.id),
            str(message.author.id),
            xp_gain
        )

        # レベルアップ通知
        if leveled_up:
            embed = discord.Embed(
                title="🎉 レベルアップ！",
                description=f"{message.author.mention} が **レベル {level}** にレベルアップしました！",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=message.author.avatar.url if message.author.avatar else None)
            await message.channel.send(embed=embed, delete_after=10)
            logger.info(f"{message.author.name} leveled up to {level}")

    @app_commands.command(name='rank', description='自分または他のユーザーのランクを表示します')
    @app_commands.describe(member='ランクを表示するユーザー（省略時は自分）')
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        """ランクを表示"""
        if member is None:
            member = interaction.user

        xp, level, messages = self.db.get_user_xp(
            str(interaction.guild.id),
            str(member.id)
        )

        # 次のレベルに必要なXP
        required_xp = (level + 1) * 100

        # ランキング順位を取得
        leaderboard = self.db.get_leaderboard(str(interaction.guild.id), limit=None)
        rank = None
        for i, (user_id, _, _, _) in enumerate(leaderboard, 1):
            if user_id == str(member.id):
                rank = i
                break

        embed = discord.Embed(
            title=f"📊 {member.name} のランク",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)

        embed.add_field(name="レベル", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp}** / {required_xp}", inline=True)
        embed.add_field(name="ランク", value=f"**#{rank}**" if rank else "未ランク", inline=True)
        embed.add_field(name="メッセージ数", value=f"**{messages}**", inline=True)

        # プログレスバー
        progress = int((xp / required_xp) * 10)
        progress_bar = "█" * progress + "░" * (10 - progress)
        embed.add_field(name="進行状況", value=f"`{progress_bar}` {int((xp/required_xp)*100)}%", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='leaderboard', description='サーバーのレベルランキングを表示します')
    @app_commands.describe(page='ページ番号（デフォルト: 1）')
    async def leaderboard(self, interaction: discord.Interaction, page: int = 1):
        """リーダーボードを表示"""
        if page < 1:
            page = 1

        per_page = 10
        offset = (page - 1) * per_page

        leaderboard = self.db.get_leaderboard(str(interaction.guild.id), limit=1000)

        if not leaderboard:
            await interaction.response.send_message(
                embed=create_error_embed("レベルデータがありません"),
                ephemeral=True
            )
            return

        # ページング
        total_pages = (len(leaderboard) + per_page - 1) // per_page
        page_data = leaderboard[offset:offset + per_page]

        embed = discord.Embed(
            title=f"🏆 レベルランキング - {interaction.guild.name}",
            description=f"ページ {page} / {total_pages}",
            color=discord.Color.gold()
        )

        for i, (user_id, xp, level, messages) in enumerate(page_data, start=offset + 1):
            member = interaction.guild.get_member(int(user_id))
            if member:
                medal = ""
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"

                embed.add_field(
                    name=f"{medal} #{i} {member.name}",
                    value=f"レベル: **{level}** | XP: **{xp}** | メッセージ: **{messages}**",
                    inline=False
                )

        embed.set_footer(text=f"あなたのランクを確認するには /rank を使用してください")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='setlevel', description='[管理者専用] ユーザーのレベルを設定します')
    @app_commands.describe(member='対象ユーザー', level='設定するレベル')
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        """ユーザーのレベルを設定（管理者専用）"""
        if level < 0:
            await interaction.response.send_message(
                embed=create_error_embed("レベルは0以上に設定してください"),
                ephemeral=True
            )
            return

        # 直接データベースを更新
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO user_levels (guild_id, user_id, xp, level, messages)
            VALUES (?, ?, 0, ?, 0)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET level = ?
        ''', (str(interaction.guild.id), str(member.id), level, level))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=create_success_embed(
                "レベル設定完了",
                f"{member.mention} のレベルを **{level}** に設定しました"
            )
        )
        logger.info(f"{interaction.user.name} set {member.name}'s level to {level}")

    @app_commands.command(name='addxp', description='[管理者専用] ユーザーにXPを追加します')
    @app_commands.describe(member='対象ユーザー', xp='追加するXP')
    @app_commands.checks.has_permissions(administrator=True)
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
        """ユーザーにXPを追加（管理者専用）"""
        if xp <= 0:
            await interaction.response.send_message(
                embed=create_error_embed("XPは1以上に設定してください"),
                ephemeral=True
            )
            return

        level, new_xp, leveled_up = self.db.add_xp(
            str(interaction.guild.id),
            str(member.id),
            xp
        )

        message = f"{member.mention} に **{xp} XP** を追加しました"
        if leveled_up:
            message += f"\n🎉 **レベル {level}** にレベルアップしました！"

        await interaction.response.send_message(
            embed=create_success_embed("XP追加完了", message)
        )
        logger.info(f"{interaction.user.name} added {xp} XP to {member.name}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
