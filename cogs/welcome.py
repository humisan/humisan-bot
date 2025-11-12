import discord
from discord.ext import commands
from discord import app_commands
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
import json
import os

logger = setup_logger(__name__)

class Welcome(commands.Cog):
    """ウェルカムメッセージ機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'welcome_config.json'
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """新しいメンバーが参加した時のイベント"""
        guild_id = str(member.guild.id)

        if guild_id not in self.config:
            return

        config = self.config[guild_id]

        # ウェルカムチャネルにメッセージを送信
        if config.get('enabled', False) and config.get('channel_id'):
            channel = member.guild.get_channel(int(config['channel_id']))
            if channel:
                message = config.get('message', 'ようこそ {mention} さん！ {server} へようこそ！')
                message = message.replace('{mention}', member.mention)
                message = message.replace('{user}', member.name)
                message = message.replace('{server}', member.guild.name)
                message = message.replace('{members}', str(member.guild.member_count))

                embed = discord.Embed(
                    title="🎉 新しいメンバーが参加しました！",
                    description=message,
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
                embed.set_footer(text=f"メンバー数: {member.guild.member_count}")

                try:
                    await channel.send(embed=embed)
                    logger.info(f"Sent welcome message for {member.name} in {member.guild.name}")
                except Exception as e:
                    logger.error(f"Error sending welcome message: {str(e)}")

        # 自動ロール付与
        if config.get('auto_role_id'):
            role = member.guild.get_role(int(config['auto_role_id']))
            if role:
                try:
                    await member.add_roles(role)
                    logger.info(f"Added auto-role {role.name} to {member.name}")
                except Exception as e:
                    logger.error(f"Error adding auto-role: {str(e)}")

    @app_commands.command(name='welcome-setup', description='ウェルカムメッセージを設定します')
    @app_commands.describe(
        channel='ウェルカムメッセージを送信するチャネル',
        message='ウェルカムメッセージ ({mention}, {user}, {server}, {members} が使えます）'
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None
    ):
        """ウェルカムメッセージを設定"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config:
            self.config[guild_id] = {}

        self.config[guild_id]['channel_id'] = str(channel.id)
        self.config[guild_id]['enabled'] = True

        if message:
            self.config[guild_id]['message'] = message

        self.save_config()

        embed = create_success_embed(
            "ウェルカムメッセージ設定完了",
            f"ウェルカムメッセージは {channel.mention} に送信されます"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"Welcome message configured for {interaction.guild.name}")

    @app_commands.command(name='welcome-toggle', description='ウェルカムメッセージの有効/無効を切り替えます')
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_toggle(self, interaction: discord.Interaction):
        """ウェルカムメッセージの有効/無効を切り替え"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config:
            await interaction.response.send_message(
                embed=create_error_embed("ウェルカムメッセージが設定されていません"),
                ephemeral=True
            )
            return

        self.config[guild_id]['enabled'] = not self.config[guild_id].get('enabled', False)
        self.save_config()

        status = "有効" if self.config[guild_id]['enabled'] else "無効"
        embed = create_success_embed(
            "ウェルカムメッセージ設定変更",
            f"ウェルカムメッセージを {status} にしました"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='welcome-autorole', description='自動ロールを設定します')
    @app_commands.describe(role='新規メンバーに自動で付与するロール')
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_autorole(self, interaction: discord.Interaction, role: discord.Role):
        """自動ロールを設定"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config:
            self.config[guild_id] = {}

        self.config[guild_id]['auto_role_id'] = str(role.id)
        self.save_config()

        embed = create_success_embed(
            "自動ロール設定完了",
            f"新規メンバーに {role.mention} が自動で付与されます"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"Auto-role configured for {interaction.guild.name}: {role.name}")

    @app_commands.command(name='welcome-test', description='ウェルカムメッセージをテストします')
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_test(self, interaction: discord.Interaction):
        """ウェルカムメッセージをテスト"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config or not self.config[guild_id].get('enabled'):
            await interaction.response.send_message(
                embed=create_error_embed("ウェルカムメッセージが設定されていないか、無効になっています"),
                ephemeral=True
            )
            return

        config = self.config[guild_id]
        channel = interaction.guild.get_channel(int(config['channel_id']))

        if not channel:
            await interaction.response.send_message(
                embed=create_error_embed("ウェルカムチャネルが見つかりません"),
                ephemeral=True
            )
            return

        message = config.get('message', 'ようこそ {mention} さん！ {server} へようこそ！')
        message = message.replace('{mention}', interaction.user.mention)
        message = message.replace('{user}', interaction.user.name)
        message = message.replace('{server}', interaction.guild.name)
        message = message.replace('{members}', str(interaction.guild.member_count))

        embed = discord.Embed(
            title="🎉 新しいメンバーが参加しました！（テスト）",
            description=message,
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
        embed.set_footer(text=f"メンバー数: {interaction.guild.member_count}")

        await channel.send(embed=embed)
        await interaction.response.send_message(
            embed=create_success_embed("テスト送信完了", f"{channel.mention} にテストメッセージを送信しました"),
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
