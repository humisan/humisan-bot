import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from datetime import timedelta
from utils.helpers import get_member_embed, create_error_embed, create_success_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Moderation(commands.Cog):
    """モデレーション・管理コマンド"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='kick', description='ユーザーをキックします')
    @app_commands.describe(member='キックするユーザー', reason='キックの理由')
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "理由なし"):
        """ユーザーをキックします"""
        try:
            if member == interaction.user:
                await interaction.response.send_message(embed=create_error_embed("自分自身をキックすることはできません"), ephemeral=True)
                return

            if member.top_role >= interaction.user.top_role:
                await interaction.response.send_message(embed=create_error_embed("このユーザーをキックする権限がありません"), ephemeral=True)
                return

            await member.kick(reason=reason)
            embed = create_success_embed(
                "キック成功",
                f"**{member.name}** をキックしました\n**理由:** {reason}"
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user.name} kicked {member.name} for: {reason}")
        except Exception as e:
            logger.error(f"Error kicking member: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("キックに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='ban', description='ユーザーをバンします')
    @app_commands.describe(member='バンするユーザー', reason='バンの理由')
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "理由なし"):
        """ユーザーをバンします"""
        try:
            if member == interaction.user:
                await interaction.response.send_message(embed=create_error_embed("自分自身をバンすることはできません"), ephemeral=True)
                return

            if member.top_role >= interaction.user.top_role:
                await interaction.response.send_message(embed=create_error_embed("このユーザーをバンする権限がありません"), ephemeral=True)
                return

            await member.ban(reason=reason)
            embed = create_success_embed(
                "バン成功",
                f"**{member.name}** をバンしました\n**理由:** {reason}"
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user.name} banned {member.name} for: {reason}")
        except Exception as e:
            logger.error(f"Error banning member: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("バンに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='unban', description='バンされたユーザーを解除します')
    @app_commands.describe(user_id='バン解除するユーザーのID')
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        """バンされたユーザーを解除します"""
        try:
            await interaction.response.defer()

            banned_users = [entry async for entry in interaction.guild.bans()]
            member_to_unban = None

            for ban_entry in banned_users:
                if str(ban_entry.user.id) == user_id or ban_entry.user.name == user_id:
                    member_to_unban = ban_entry.user
                    break

            if member_to_unban is None:
                await interaction.followup.send(embed=create_error_embed(f"ユーザー '{user_id}' はバンリストに見つかりません"))
                return

            await interaction.guild.unban(member_to_unban)
            embed = create_success_embed(
                "バン解除成功",
                f"**{member_to_unban.name}** のバンを解除しました"
            )
            await interaction.followup.send(embed=embed)
            logger.info(f"{interaction.user.name} unbanned {member_to_unban.name}")
        except Exception as e:
            logger.error(f"Error unbanning member: {str(e)}")
            await interaction.followup.send(embed=create_error_embed("バン解除に失敗しました", str(e)))

    @app_commands.command(name='timeout', description='ユーザーをタイムアウトします')
    @app_commands.describe(member='タイムアウトするユーザー', duration='タイムアウト時間（秒）', reason='理由')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "理由なし"):
        """ユーザーをタイムアウトします"""
        try:
            if duration < 1 or duration > 2419200:  # 最大28日
                await interaction.response.send_message(embed=create_error_embed("タイムアウト時間は1秒から2419200秒（28日）の間に設定してください"), ephemeral=True)
                return

            await member.timeout(timedelta(seconds=duration), reason=reason)

            embed = create_success_embed(
                "タイムアウト成功",
                f"**{member.name}** を {duration} 秒間タイムアウトしました\n**理由:** {reason}"
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user.name} timed out {member.name} for {duration}s: {reason}")
        except Exception as e:
            logger.error(f"Error timing out member: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("タイムアウトに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='untimeout', description='ユーザーのタイムアウトを解除します')
    @app_commands.describe(member='タイムアウト解除するユーザー')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        """ユーザーのタイムアウトを解除します"""
        try:
            await member.timeout(None)
            embed = create_success_embed(
                "タイムアウト解除成功",
                f"**{member.name}** のタイムアウトを解除しました"
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user.name} removed timeout from {member.name}")
        except Exception as e:
            logger.error(f"Error removing timeout: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("タイムアウト解除に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='warn', description='ユーザーに警告を与えます')
    @app_commands.describe(member='警告するユーザー', reason='警告の理由')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "理由なし"):
        """ユーザーに警告を与えます"""
        try:
            embed = discord.Embed(
                title="⚠️ 警告",
                description=f"{interaction.user.mention} があなたに警告を与えました\n**理由:** {reason}",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                pass

            await interaction.response.send_message(embed=create_success_embed(
                "警告成功",
                f"**{member.name}** に警告を与えました\n**理由:** {reason}"
            ))
            logger.info(f"{interaction.user.name} warned {member.name} for: {reason}")
        except Exception as e:
            logger.error(f"Error warning member: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("警告に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='clear', description='メッセージを削除します')
    @app_commands.describe(amount='削除するメッセージ数（1〜100）')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int = 5):
        """メッセージを削除します"""
        try:
            if amount < 1 or amount > 100:
                await interaction.response.send_message(embed=create_error_embed("削除数は1〜100の間に設定してください"), ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=amount)

            embed = create_success_embed(
                "削除成功",
                f"{len(deleted)} 件のメッセージを削除しました"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"{interaction.user.name} cleared {len(deleted)} messages")
        except Exception as e:
            logger.error(f"Error clearing messages: {str(e)}")
            await interaction.followup.send(embed=create_error_embed("削除に失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='userinfo', description='ユーザー情報を表示します')
    @app_commands.describe(member='情報を表示するユーザー（省略時は自分）')
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        """ユーザー情報を表示します"""
        try:
            if member is None:
                member = interaction.user

            embed = get_member_embed(member)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ユーザー情報の取得に失敗しました", str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
