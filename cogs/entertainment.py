import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Entertainment(commands.Cog):
    """エンターテイメント機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
