import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from typing import Optional
from utils.helpers import create_error_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Connect4Game:
    """四目並べゲーム管理クラス"""

    ROWS = 6
    COLS = 7
    EMPTY = 0
    PLAYER1 = 1
    PLAYER2 = 2

    EMPTY_EMOJI = "⬜"
    P1_EMOJI = "🔴"
    P2_EMOJI = "🟡"

    COLUMN_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]

    def __init__(self, player1: discord.User, player2: discord.User):
        self.player1 = player1
        self.player2 = player2
        self.board = [[self.EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.current_player = self.PLAYER1
        self.game_over = False
        self.winner = None
        self.column_heights = [0] * self.COLS

    def drop_piece(self, col: int) -> bool:
        """列にピースをドロップ"""
        if col < 0 or col >= self.COLS:
            return False

        if self.column_heights[col] >= self.ROWS:
            return False

        row = self.ROWS - 1 - self.column_heights[col]
        self.board[row][col] = self.current_player
        self.column_heights[col] += 1

        return True

    def check_winner(self) -> bool:
        """勝者判定"""
        # 水平チェック
        for row in range(self.ROWS):
            for col in range(self.COLS - 3):
                if (self.board[row][col] != self.EMPTY and
                    self.board[row][col] == self.board[row][col+1] ==
                    self.board[row][col+2] == self.board[row][col+3]):
                    return True

        # 垂直チェック
        for col in range(self.COLS):
            for row in range(self.ROWS - 3):
                if (self.board[row][col] != self.EMPTY and
                    self.board[row][col] == self.board[row+1][col] ==
                    self.board[row+2][col] == self.board[row+3][col]):
                    return True

        # 斜め（↘︎）チェック
        for row in range(self.ROWS - 3):
            for col in range(self.COLS - 3):
                if (self.board[row][col] != self.EMPTY and
                    self.board[row][col] == self.board[row+1][col+1] ==
                    self.board[row+2][col+2] == self.board[row+3][col+3]):
                    return True

        # 斜め（↙︎）チェック
        for row in range(self.ROWS - 3):
            for col in range(3, self.COLS):
                if (self.board[row][col] != self.EMPTY and
                    self.board[row][col] == self.board[row+1][col-1] ==
                    self.board[row+2][col-2] == self.board[row+3][col-3]):
                    return True

        return False

    def is_board_full(self) -> bool:
        """盤面が満杯か判定"""
        return all(height >= self.ROWS for height in self.column_heights)

    def get_board_display(self) -> str:
        """盤面を表示文字列に変換"""
        display = ""
        for row in range(self.ROWS):
            for col in range(self.COLS):
                cell = self.board[row][col]
                if cell == self.EMPTY:
                    display += self.EMPTY_EMOJI
                elif cell == self.PLAYER1:
                    display += self.P1_EMOJI
                else:
                    display += self.P2_EMOJI
            display += "\n"

        # 列番号を表示
        display += "".join(self.COLUMN_EMOJIS)
        return display

    def switch_player(self):
        """プレイヤーを切り替え"""
        self.current_player = self.PLAYER2 if self.current_player == self.PLAYER1 else self.PLAYER1


class Games(commands.Cog):
    """ゲーム機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games = {}

    def is_game_running(self, channel_id: int) -> bool:
        """このチャンネルでゲーム中か判定"""
        return channel_id in self.active_games

    @app_commands.command(name='connect4', description='四目並べを開始します')
    @app_commands.describe(opponent='対戦相手のメンション')
    async def connect4(self, interaction: discord.Interaction, opponent: discord.User):
        """四目並べゲーム開始"""
        try:
            if interaction.user.id == opponent.id:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="自分自身と対戦することはできません",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if opponent.bot:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="ボットと対戦することはできません",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if self.is_game_running(interaction.channel_id):
                embed = discord.Embed(
                    title="❌ エラー",
                    description="このチャンネルで既にゲーム中です",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            game = Connect4Game(interaction.user, opponent)
            self.active_games[interaction.channel_id] = game

            embed = discord.Embed(
                title="🎮 四目並べ",
                description=f"{interaction.user.mention} vs {opponent.mention}\n\n{game.get_board_display()}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"次のターン: {interaction.user.name} ({game.P1_EMOJI})")

            await interaction.response.send_message(embed=embed)
            msg = await interaction.original_response()

            # リアクション追加
            for emoji in Connect4Game.COLUMN_EMOJIS:
                await msg.add_reaction(emoji)

            # ゲームループ
            await self.game_loop(msg, game, interaction.channel_id)

        except Exception as e:
            logger.error(f"Error in connect4 command: {str(e)}")
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=create_error_embed("四目並べエラー", str(e)), ephemeral=True)

    async def game_loop(self, message: discord.Message, game: Connect4Game, channel_id: int):
        """ゲームループ"""
        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            current_player = game.player1 if game.current_player == Connect4Game.PLAYER1 else game.player2
            return (
                reaction.message.id == message.id and
                user.id == current_player.id and
                str(reaction.emoji) in Connect4Game.COLUMN_EMOJIS
            )

        while not game.game_over:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=300, check=check)

                col = Connect4Game.COLUMN_EMOJIS.index(str(reaction.emoji))

                # 列が満杯の場合
                if game.column_heights[col] >= Connect4Game.ROWS:
                    await message.remove_reaction(reaction.emoji, user)
                    continue

                # ピースをドロップ
                game.drop_piece(col)

                # 勝者判定
                if game.check_winner():
                    winner = game.player1 if game.current_player == Connect4Game.PLAYER1 else game.player2
                    game.game_over = True
                    game.winner = winner

                    embed = discord.Embed(
                        title="🎉 ゲーム終了",
                        description=f"{winner.mention} の勝利！\n\n{game.get_board_display()}",
                        color=discord.Color.gold(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text="おめでとうございます！")
                    await message.edit(embed=embed)

                elif game.is_board_full():
                    game.game_over = True

                    embed = discord.Embed(
                        title="🤝 ゲーム終了",
                        description=f"盤面が満杯になりました。引き分けです。\n\n{game.get_board_display()}",
                        color=discord.Color.greyple(),
                        timestamp=discord.utils.utcnow()
                    )
                    await message.edit(embed=embed)

                else:
                    # 次のプレイヤーへ
                    game.switch_player()
                    current_player = game.player1 if game.current_player == Connect4Game.PLAYER1 else game.player2
                    emoji = game.P1_EMOJI if game.current_player == Connect4Game.PLAYER1 else game.P2_EMOJI

                    embed = discord.Embed(
                        title="🎮 四目並べ",
                        description=f"{game.player1.mention} vs {game.player2.mention}\n\n{game.get_board_display()}",
                        color=discord.Color.blue(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text=f"次のターン: {current_player.name} ({emoji})")
                    await message.edit(embed=embed)

                # リアクション削除
                await message.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                game.game_over = True
                embed = discord.Embed(
                    title="⏱️ ゲーム中止",
                    description="5分以上操作がなかったためゲームを中止しました。",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
                await message.edit(embed=embed)
                break

            except Exception as e:
                logger.error(f"Error in game loop: {str(e)}")
                break

        # ゲーム終了時にアクティブゲームから削除
        if channel_id in self.active_games:
            del self.active_games[channel_id]


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
