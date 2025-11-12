import discord
from discord.ext import commands
from discord import app_commands
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
from typing import List

logger = setup_logger(__name__)

class PollView(discord.ui.View):
    """投票用のボタンビュー"""

    def __init__(self, options: List[str]):
        super().__init__(timeout=None)
        self.votes = {option: set() for option in options}

        # 各選択肢にボタンを追加
        for i, option in enumerate(options[:5]):  # 最大5つまで
            button = discord.ui.Button(
                label=f"{option} (0)",
                style=discord.ButtonStyle.primary,
                custom_id=f"poll_{i}"
            )
            button.callback = self.create_callback(option, button)
            self.add_item(button)

    def create_callback(self, option: str, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            user_id = interaction.user.id

            # 既に投票している場合は取り消し
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
                await interaction.response.send_message("投票を取り消しました", ephemeral=True)
            else:
                # 他の選択肢から投票を削除（単一選択の場合）
                for opt in self.votes:
                    if user_id in self.votes[opt]:
                        self.votes[opt].remove(user_id)

                self.votes[option].add(user_id)
                await interaction.response.send_message(f"「{option}」に投票しました", ephemeral=True)

            # ボタンのラベルを更新
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    for opt, voters in self.votes.items():
                        if opt in item.label:
                            item.label = f"{opt} ({len(voters)})"
                            break

            # メッセージを更新
            await interaction.message.edit(view=self)

        return callback


class Polls(commands.Cog):
    """投票・アンケート機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='poll', description='投票を作成します')
    @app_commands.describe(
        question='投票の質問',
        option1='選択肢1',
        option2='選択肢2',
        option3='選択肢3（任意）',
        option4='選択肢4（任意）',
        option5='選択肢5（任意）'
    )
    async def create_poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str = None,
        option4: str = None,
        option5: str = None
    ):
        """投票を作成"""
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)
        if option5:
            options.append(option5)

        embed = discord.Embed(
            title="📊 投票",
            description=f"**{question}**\n\n以下のボタンをクリックして投票してください",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"作成者: {interaction.user.name}")

        view = PollView(options)
        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"{interaction.user.name} created a poll: {question}")

    @app_commands.command(name='quickpoll', description='はい/いいえの簡易投票を作成します')
    @app_commands.describe(question='投票の質問')
    async def quick_poll(self, interaction: discord.Interaction, question: str):
        """はい/いいえ投票を作成"""
        embed = discord.Embed(
            title="📊 簡易投票",
            description=f"**{question}**",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"作成者: {interaction.user.name}")

        # リアクションベースの投票
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        await message.add_reaction("👍")
        await message.add_reaction("👎")
        logger.info(f"{interaction.user.name} created a quick poll: {question}")

    @app_commands.command(name='pollresult', description='投票結果を表示します')
    @app_commands.describe(message_id='投票メッセージのID')
    async def poll_result(self, interaction: discord.Interaction, message_id: str):
        """投票結果を表示"""
        try:
            message = await interaction.channel.fetch_message(int(message_id))

            if not message.embeds:
                await interaction.response.send_message(
                    embed=create_error_embed("投票メッセージが見つかりません"),
                    ephemeral=True
                )
                return

            # リアクションベースの投票結果
            if message.reactions:
                embed = discord.Embed(
                    title="📊 投票結果",
                    description=f"**{message.embeds[0].description}**",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )

                for reaction in message.reactions:
                    embed.add_field(
                        name=f"{reaction.emoji}",
                        value=f"{reaction.count - 1} 票",  # ボット自身の反応を除く
                        inline=True
                    )

                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    embed=create_error_embed("投票結果が見つかりません"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error fetching poll result: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("投票結果の取得に失敗しました", str(e)),
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))
