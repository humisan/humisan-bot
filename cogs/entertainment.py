import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
import math
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Entertainment(commands.Cog):
    """エンターテイメント機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def split_choices_into_groups(choices: list[str]) -> list[list[str]]:
        """候補を均等に複数グループに分割"""
        if len(choices) <= 5:
            return [choices]

        num_groups = math.ceil(len(choices) / 3)
        group_size = math.ceil(len(choices) / num_groups)

        groups = []
        for i in range(0, len(choices), group_size):
            groups.append(choices[i:i + group_size])

        return groups

    @staticmethod
    def assign_to_teams(members: list[str], team_size: int = 3) -> list[list[str]]:
        """メンバーをチームに割り当てる（奇数対応）"""
        shuffled = members.copy()
        random.shuffle(shuffled)

        teams = []
        for i in range(0, len(shuffled), team_size):
            teams.append(shuffled[i:i + team_size])

        return teams

    @commands.command(name='roll', description='複数の候補からランダムに1つを選択します')
    async def roll_prefix(self, ctx: commands.Context, *, choices: str):
        """複数の候補からランダムに1つを選択します

        使用例: !roll りんご,みかん,バナナ
        """
        try:
            if not choices or ',' not in choices:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="カンマで区切られた複数の候補を入力してください\n例: `!roll りんご,みかん,バナナ`",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            choice_list = [c.strip() for c in choices.split(',')]
            choice_list = [c for c in choice_list if c]

            if len(choice_list) < 2:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="2つ以上の候補を入力してください",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            selected = random.choice(choice_list)
            groups = self.split_choices_into_groups(choice_list)

            embed = discord.Embed(
                title="🎲 ロール結果",
                description=f"**選ばれたのは:** `{selected}`",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )

            for idx, group in enumerate(groups, 1):
                field_value = "\n".join([f"• {choice}" for choice in group])
                embed.add_field(
                    name=f"候補 {idx}" if len(groups) > 1 else "候補",
                    value=field_value,
                    inline=len(groups) > 1
                )

            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in roll command: {str(e)}")
            embed = discord.Embed(
                title="❌ エラー",
                description=f"ロール処理中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @app_commands.command(name='roll', description='複数の候補からランダムに1つを選択します')
    @app_commands.describe(choices='カンマで区切られた複数の候補（例: りんご,みかん,バナナ）')
    async def roll_slash(self, interaction: discord.Interaction, choices: str):
        """複数の候補からランダムに1つを選択します"""
        try:
            if not choices or ',' not in choices:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="カンマで区切られた複数の候補を入力してください\n例: `りんご,みかん,バナナ`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            choice_list = [c.strip() for c in choices.split(',')]
            choice_list = [c for c in choice_list if c]

            if len(choice_list) < 2:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="2つ以上の候補を入力してください",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            selected = random.choice(choice_list)
            groups = self.split_choices_into_groups(choice_list)

            embed = discord.Embed(
                title="🎲 ロール結果",
                description=f"**選ばれたのは:** `{selected}`",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )

            for idx, group in enumerate(groups, 1):
                field_value = "\n".join([f"• {choice}" for choice in group])
                embed.add_field(
                    name=f"候補 {idx}" if len(groups) > 1 else "候補",
                    value=field_value,
                    inline=len(groups) > 1
                )

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in roll slash command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ロール処理エラー", str(e)), ephemeral=True)

    @commands.command(name='hoplite', description='メンバーを3人チームに割り当てます')
    async def hoplite_prefix(self, ctx: commands.Context, *, members: str):
        """メンバーを3人チームに割り当てます

        使用例: !hoplite 太郎,次郎,三郎,四郎,五郎,六郎
        """
        try:
            if not members or ',' not in members:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="カンマで区切られた複数のメンバーを入力してください\n例: `!hoplite 太郎,次郎,三郎,四郎`",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            member_list = [m.strip() for m in members.split(',')]
            member_list = [m for m in member_list if m]

            if len(member_list) < 2:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="2人以上のメンバーを入力してください",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            teams = self.assign_to_teams(member_list)

            embed = discord.Embed(
                title="🛡️ チーム割り当て結果",
                description=f"**合計 {len(member_list)} 人を {len(teams)} チームに割り当てました**",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            for idx, team in enumerate(teams, 1):
                team_members = "\n".join([f"• {member}" for member in team])
                embed.add_field(
                    name=f"チーム {idx} ({len(team)}人)",
                    value=team_members,
                    inline=False
                )

            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in hoplite command: {str(e)}")
            embed = discord.Embed(
                title="❌ エラー",
                description=f"チーム割り当て処理中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @app_commands.command(name='hoplite', description='メンバーを3人チームに割り当てます')
    @app_commands.describe(members='カンマで区切られた複数のメンバー（例: 太郎,次郎,三郎,四郎）')
    async def hoplite_slash(self, interaction: discord.Interaction, members: str):
        """メンバーを3人チームに割り当てます"""
        try:
            if not members or ',' not in members:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="カンマで区切られた複数のメンバーを入力してください\n例: `太郎,次郎,三郎,四郎`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            member_list = [m.strip() for m in members.split(',')]
            member_list = [m for m in member_list if m]

            if len(member_list) < 2:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="2人以上のメンバーを入力してください",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            teams = self.assign_to_teams(member_list)

            embed = discord.Embed(
                title="🛡️ チーム割り当て結果",
                description=f"**合計 {len(member_list)} 人を {len(teams)} チームに割り当てました**",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )

            for idx, team in enumerate(teams, 1):
                team_members = "\n".join([f"• {member}" for member in team])
                embed.add_field(
                    name=f"チーム {idx} ({len(team)}人)",
                    value=team_members,
                    inline=False
                )

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in hoplite slash command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("チーム割り当てエラー", str(e)), ephemeral=True)

    @app_commands.command(name='ping', description='ボットのピングを表示します')
    async def ping(self, interaction: discord.Interaction):
        """ボットのピングを表示します"""
        try:
            latency = round(self.bot.latency * 1000)
            embed = discord.Embed(
                title="🏓 Ping",
                description=f"**ボットのレイテンシ:** {latency}ms",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in ping command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ピング取得に失敗しました", str(e)), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Entertainment(bot))
