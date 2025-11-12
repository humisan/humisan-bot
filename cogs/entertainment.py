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

    @app_commands.command(name='8ball', description='8ボール占いをします')
    @app_commands.describe(question='占いたい質問')
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        """8ボール占いをします"""
        try:
            responses = [
                "いい回答だね",
                "間違いなく",
                "そのようだ",
                "はっきり、そう",
                "おそらく",
                "おそらくそうだ",
                "うーん、わからない",
                "わかりません",
                "聞き直してください",
                "そうではないようです",
                "ちょっと疑わしい",
                "否定的です",
                "まずあり得ません",
                "ありえません",
            ]

            embed = discord.Embed(
                title="🎱 8ボール占い",
                description=f"**質問:** {question}\n\n**回答:** {random.choice(responses)}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"質問者: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in 8ball command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("8ボール占いに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='rps', description='じゃんけんをします')
    @app_commands.describe(choice='rock（石）、paper（紙）、scissors（はさみ）のいずれか')
    @app_commands.choices(choice=[
        app_commands.Choice(name='石 (Rock)', value='rock'),
        app_commands.Choice(name='紙 (Paper)', value='paper'),
        app_commands.Choice(name='はさみ (Scissors)', value='scissors')
    ])
    async def rock_paper_scissors(self, interaction: discord.Interaction, choice: str):
        """じゃんけんをします"""
        try:
            user_choice = choice.lower()
            bot_choice = random.choice(['rock', 'paper', 'scissors'])

            results = {
                ('rock', 'scissors'): "あなたの勝ち！🎉",
                ('paper', 'rock'): "あなたの勝ち！🎉",
                ('scissors', 'paper'): "あなたの勝ち！🎉",
                ('rock', 'rock'): "引き分け！🤝",
                ('paper', 'paper'): "引き分け！🤝",
                ('scissors', 'scissors'): "引き分け！🤝",
            }

            result = results.get((user_choice, bot_choice), "ボットの勝ち！")

            choice_emoji = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
            choice_name = {'rock': '石', 'paper': '紙', 'scissors': 'はさみ'}

            embed = discord.Embed(
                title="じゃんけん",
                description=f"**あなた:** {choice_emoji[user_choice]} {choice_name[user_choice]}\n"
                            f"**ボット:** {choice_emoji[bot_choice]} {choice_name[bot_choice]}\n\n"
                            f"**結果:** {result}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in rps command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("じゃんけんに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='dice', description='サイコロを振ります')
    @app_commands.describe(sides='サイコロの面数（デフォルト: 6）')
    async def dice(self, interaction: discord.Interaction, sides: int = 6):
        """サイコロを振ります"""
        try:
            if sides < 2:
                await interaction.response.send_message(embed=create_error_embed("サイコロの面は2以上にしてください"), ephemeral=True)
                return

            roll = random.randint(1, sides)
            embed = discord.Embed(
                title="🎲 サイコロ",
                description=f"**{sides}面のサイコロを振りました！**\n\n結果: **{roll}**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"振った人: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in dice command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("サイコロを振るのに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='flip', description='コインを投げます')
    async def flip(self, interaction: discord.Interaction):
        """コインを投げます"""
        try:
            result = random.choice(['表', '裏'])
            emoji = '🪙'

            embed = discord.Embed(
                title="コイン投げ",
                description=f"{emoji} **{result}**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"投げた人: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in flip command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("コインを投げるのに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='joke', description='ランダムにジョークを言います')
    async def joke(self, interaction: discord.Interaction):
        """ランダムにジョークを言います"""
        try:
            jokes = [
                "なぜプログラマーはハロウィンが好きなのか？ なぜなら Oct と Dec は同じだから！",
                "プログラマーが仕事から帰ってくると、妻が言った：『別の男があなたの代わりを提案している』彼は答えた：『ん、何を言ってるの？』妻は答えた：『AIアシスタント。'",
                "バグ報告：特定の条件下でプログラムが正常に動作する場合があります。",
                "バグはいつどこでも見つかる。なぜなら、それらは開発者が隠した場所にあるから。",
                "プログラマーの3つの難しいこと：1. キャッシュ無効化、2. 名前付け、3. オフバイワンエラー。",
                "なぜプログラマーはダークモードを使うのか？ライトがバグを引き寄せるから！",
                "「今日は10時間働いた」「何を作ったの？」「バグを直して元に戻した」",
            ]

            embed = discord.Embed(
                title="😄 ジョーク",
                description=random.choice(jokes),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in joke command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("ジョークを言うのに失敗しました", str(e)), ephemeral=True)

    @app_commands.command(name='choose', description='複数の選択肢から1つを選びます')
    @app_commands.describe(options='選択肢をカンマ区切りで入力（例: りんご, バナナ, オレンジ）')
    async def choose(self, interaction: discord.Interaction, options: str):
        """複数の選択肢から1つを選びます"""
        try:
            choices = [option.strip() for option in options.split(',')]

            if len(choices) < 2:
                await interaction.response.send_message(embed=create_error_embed("最低2つの選択肢が必要です"), ephemeral=True)
                return

            selected = random.choice(choices)

            embed = discord.Embed(
                title="🎯 選択",
                description=f"**選択肢:** {', '.join(choices)}\n\n**選ばれた:** {selected}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in choose command: {str(e)}")
            await interaction.response.send_message(embed=create_error_embed("選択に失敗しました", str(e)), ephemeral=True)

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
