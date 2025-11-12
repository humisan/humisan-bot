import discord
from discord.ext import commands
from discord import app_commands
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
import json
import os

logger = setup_logger(__name__)

class TicketView(discord.ui.View):
    """チケット作成用のボタン"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 チケットを作成", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """チケット作成ボタン"""
        await interaction.response.defer(ephemeral=True)

        # 既存のチケットチャネルを確認
        for channel in interaction.guild.text_channels:
            if channel.name == f"ticket-{interaction.user.name.lower()}":
                await interaction.followup.send(
                    embed=create_error_embed("既にチケットが存在します", f"{channel.mention} を確認してください"),
                    ephemeral=True
                )
                return

        # カテゴリを取得
        category = discord.utils.get(interaction.guild.categories, name="Tickets")
        if not category:
            category = await interaction.guild.create_category("Tickets")

        # チケットチャネルを作成
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        # チケット情報の埋め込み
        embed = discord.Embed(
            title="🎫 チケットが作成されました",
            description=f"ようこそ {interaction.user.mention} さん！\n\nサポートスタッフが対応するまでお待ちください。\n問題を詳しく説明してください。",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"チケット作成者: {interaction.user.name}")

        close_view = CloseTicketView()
        await channel.send(f"{interaction.user.mention}", embed=embed, view=close_view)

        await interaction.followup.send(
            embed=create_success_embed("チケット作成完了", f"チケットを作成しました: {channel.mention}"),
            ephemeral=True
        )
        logger.info(f"Ticket created by {interaction.user.name}")


class CloseTicketView(discord.ui.View):
    """チケットクローズ用のボタン"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """チケットクローズボタン"""
        await interaction.response.defer()

        embed = discord.Embed(
            title="🔒 チケットをクローズしています...",
            description="5秒後にこのチャネルが削除されます",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

        logger.info(f"Ticket {interaction.channel.name} closed by {interaction.user.name}")

        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()


class Tickets(commands.Cog):
    """チケットシステム"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'ticket_config.json'
        self.config = self.load_config()

    def load_config(self):
        """設定を読み込む"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_config(self):
        """設定を保存する"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    @app_commands.command(name='ticket-setup', description='チケットシステムをセットアップします')
    @app_commands.describe(channel='チケット作成ボタンを配置するチャネル')
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """チケットシステムをセットアップ"""
        embed = discord.Embed(
            title="🎫 チケットシステム",
            description="サポートが必要な場合は、下のボタンをクリックしてチケットを作成してください。\n\n"
                       "チケットを作成すると、あなた専用のプライベートチャネルが作成されます。",
            color=discord.Color.blue()
        )
        embed.add_field(name="📝 使い方", value="1. 下のボタンをクリック\n2. チケットチャネルで問題を説明\n3. サポートを待つ", inline=False)

        view = TicketView()
        await channel.send(embed=embed, view=view)

        guild_id = str(interaction.guild.id)
        self.config[guild_id] = {'channel_id': str(channel.id)}
        self.save_config()

        await interaction.response.send_message(
            embed=create_success_embed("チケットシステム設定完了", f"{channel.mention} にチケットシステムを設定しました"),
            ephemeral=True
        )
        logger.info(f"Ticket system configured for {interaction.guild.name}")

    @app_commands.command(name='ticket-add', description='チケットにユーザーを追加します')
    @app_commands.describe(user='追加するユーザー')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        """チケットにユーザーを追加"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはチケットチャネルでのみ使用できます"),
                ephemeral=True
            )
            return

        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
        await interaction.response.send_message(
            embed=create_success_embed("ユーザー追加完了", f"{user.mention} をこのチケットに追加しました")
        )
        logger.info(f"Added {user.name} to ticket {interaction.channel.name}")

    @app_commands.command(name='ticket-remove', description='チケットからユーザーを削除します')
    @app_commands.describe(user='削除するユーザー')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_remove(self, interaction: discord.Interaction, user: discord.Member):
        """チケットからユーザーを削除"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはチケットチャネルでのみ使用できます"),
                ephemeral=True
            )
            return

        await interaction.channel.set_permissions(user, read_messages=False)
        await interaction.response.send_message(
            embed=create_success_embed("ユーザー削除完了", f"{user.mention} をこのチケットから削除しました")
        )
        logger.info(f"Removed {user.name} from ticket {interaction.channel.name}")

    @app_commands.command(name='ticket-close', description='チケットを閉じます')
    async def ticket_close(self, interaction: discord.Interaction):
        """チケットを閉じる"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはチケットチャネルでのみ使用できます"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        embed = discord.Embed(
            title="🔒 チケットをクローズしています...",
            description="5秒後にこのチャネルが削除されます",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

        logger.info(f"Ticket {interaction.channel.name} closed by {interaction.user.name}")

        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
