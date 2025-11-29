import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
from typing import Optional
from utils.helpers import create_error_embed, send_error_to_discord
from utils.logger import setup_logger
import traceback

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
        self.last_move_col = None

    def drop_piece(self, col: int) -> bool:
        """列にピースをドロップ"""
        if col < 0 or col >= self.COLS:
            return False

        if self.column_heights[col] >= self.ROWS:
            return False

        row = self.ROWS - 1 - self.column_heights[col]
        self.board[row][col] = self.current_player
        self.column_heights[col] += 1
        self.last_move_col = col

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


class Connect4View(ui.View):
    """四目並べ用ボタンビュー"""

    def __init__(self, game: 'Connect4Game', timeout: int = 300):
        super().__init__(timeout=timeout)
        self.game = game
        self.game_over = False

        # 各列のボタンを作成
        for col in range(Connect4Game.COLS):
            button = ui.Button(
                label=str(col + 1),
                style=discord.ButtonStyle.primary,
                custom_id=f"connect4_col_{col}"
            )
            button.callback = self.make_column_callback(col)
            self.add_item(button)

    def make_column_callback(self, col: int):
        async def callback(interaction: discord.Interaction):
            current_player = self.game.player1 if self.game.current_player == Connect4Game.PLAYER1 else self.game.player2

            if interaction.user.id != current_player.id:
                await interaction.response.send_message(
                    "あなたのターンではありません",
                    ephemeral=True
                )
                return

            if self.game_over:
                await interaction.response.send_message(
                    "ゲームは既に終了しています",
                    ephemeral=True
                )
                return

            if self.game.column_heights[col] >= Connect4Game.ROWS:
                await interaction.response.send_message(
                    "その列は満杯です",
                    ephemeral=True
                )
                return

            self.game.drop_piece(col)

            # 勝者判定前にプレイヤーを切り替える
            if self.game.check_winner():
                self.game.game_over = True
                self.game_over = True
            else:
                self.game.switch_player()

            await interaction.response.defer()

        return callback

    async def on_timeout(self):
        self.game_over = True


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

            view = Connect4View(game)
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # ゲームループ
            await self.game_loop(msg, game, view, interaction.channel_id)

        except Exception as e:
            error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
            logger.error(f"Error in connect4 command: {error_message}")
            await send_error_to_discord(
                self.bot,
                "四目並べコマンドエラー",
                error_message,
                "コマンドエラー"
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=create_error_embed("四目並べエラー", str(e)), ephemeral=True)

    async def game_loop(self, message: discord.Message, game: Connect4Game, view: Connect4View, channel_id: int):
        """ゲームループ"""
        last_displayed_state = str(game.board)

        while not game.game_over and not view.game_over:
            try:
                await asyncio.sleep(0.5)

                # ゲーム状態が変わっていなければスキップ
                current_state = str(game.board)
                if current_state == last_displayed_state:
                    continue

                last_displayed_state = current_state

                # 勝者判定（既に勝利状態）
                if game.game_over:
                    # 現在のプレイヤーが勝者（既にswitch前のプレイヤーが勝利ピースを置いた）
                    winner = game.player1 if game.current_player == Connect4Game.PLAYER2 else game.player2
                    view.game_over = True

                    embed = discord.Embed(
                        title="🎉 ゲーム終了",
                        description=f"{winner.mention} の勝利！\n\n{game.get_board_display()}",
                        color=discord.Color.gold(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text="おめでとうございます！")
                    await message.edit(embed=embed, view=None)
                    break

                elif game.is_board_full():
                    game.game_over = True
                    view.game_over = True

                    embed = discord.Embed(
                        title="🤝 ゲーム終了",
                        description=f"盤面が満杯になりました。引き分けです。\n\n{game.get_board_display()}",
                        color=discord.Color.greyple(),
                        timestamp=discord.utils.utcnow()
                    )
                    await message.edit(embed=embed, view=None)
                    break

                else:
                    # 盤面を更新
                    current_player = game.player1 if game.current_player == Connect4Game.PLAYER1 else game.player2
                    emoji = game.P1_EMOJI if game.current_player == Connect4Game.PLAYER1 else game.P2_EMOJI

                    embed = discord.Embed(
                        title="🎮 四目並べ",
                        description=f"{game.player1.mention} vs {game.player2.mention}\n\n{game.get_board_display()}",
                        color=discord.Color.blue(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text=f"次のターン: {current_player.name} ({emoji})")
                    await message.edit(embed=embed, view=view)

            except Exception as e:
                error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
                logger.error(f"Error in game loop: {error_message}")
                await send_error_to_discord(
                    self.bot,
                    "四目並べゲームループエラー",
                    error_message,
                    "ゲームエラー"
                )
                break

        # ゲーム終了時にアクティブゲームから削除
        if channel_id in self.active_games:
            del self.active_games[channel_id]


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
