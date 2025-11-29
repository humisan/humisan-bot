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

    @app_commands.command(name='othello', description='オセロ/リバーシを開始します')
    @app_commands.describe(opponent='対戦相手のメンション')
    async def othello(self, interaction: discord.Interaction, opponent: discord.User):
        """オセロ/リバーシゲーム開始"""
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

            game = OthelloGame(interaction.user, opponent)
            self.active_games[interaction.channel_id] = game

            black_score, white_score = game.get_score()
            embed = discord.Embed(
                title="⚫⚪ オセロ/リバーシ",
                description=f"{interaction.user.mention} (⚫黒) vs {opponent.mention} (⚪白)\n\n{game.get_board_display()}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="スコア", value=f"⚫: {black_score} | ⚪: {white_score}", inline=False)
            embed.set_footer(text=f"次のターン: {interaction.user.name} (⚫黒)")

            view = OthelloView(game)
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # ゲームループ
            await self.othello_game_loop(msg, game, view, interaction.channel_id)

        except Exception as e:
            error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
            logger.error(f"Error in othello command: {error_message}")
            await send_error_to_discord(
                self.bot,
                "オセロコマンドエラー",
                error_message,
                "コマンドエラー"
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=create_error_embed("オセロエラー", str(e)), ephemeral=True)

    async def othello_game_loop(self, message: discord.Message, game: OthelloGame, view: OthelloView, channel_id: int):
        """オセロゲームループ"""
        while not game.game_over and not view.game_over:
            try:
                await asyncio.sleep(0.5)

                # ゲーム終了判定
                if game.check_game_over():
                    black_score, white_score = game.get_score()
                    winner = "⚫黒" if black_score > white_score else ("⚪白" if white_score > black_score else "引き分け")

                    embed = discord.Embed(
                        title="🎉 ゲーム終了",
                        description=f"{winner}の勝利！\n\n{game.get_board_display()}",
                        color=discord.Color.gold(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="最終スコア", value=f"⚫: {black_score} | ⚪: {white_score}", inline=False)
                    await message.edit(embed=embed, view=None)
                    break

                # 有効な手がない場合
                valid_moves = game.get_valid_moves()
                if not valid_moves:
                    current_player_name = game.player1.name if game.current_player == OthelloGame.BLACK else game.player2.name
                    embed = discord.Embed(
                        title="📢 パス",
                        description=f"{current_player_name}は有効な手がないため、パスします。",
                        color=discord.Color.orange()
                    )
                    await message.channel.send(embed=embed)
                    game.switch_player()
                    continue

                # 盤面更新
                current_player = game.player1 if game.current_player == OthelloGame.BLACK else game.player2
                emoji = "⚫" if game.current_player == OthelloGame.BLACK else "⚪"
                black_score, white_score = game.get_score()

                embed = discord.Embed(
                    title="⚫⚪ オセロ/リバーシ",
                    description=f"{game.player1.mention} (⚫黒) vs {game.player2.mention} (⚪白)\n\n{game.get_board_display()}",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="スコア", value=f"⚫: {black_score} | ⚪: {white_score}", inline=False)
                embed.set_footer(text=f"次のターン: {current_player.name} ({emoji})")
                await message.edit(embed=embed, view=view)

            except Exception as e:
                error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
                logger.error(f"Error in othello game loop: {error_message}")
                await send_error_to_discord(
                    self.bot,
                    "オセロゲームループエラー",
                    error_message,
                    "ゲームエラー"
                )
                break

        # ゲーム終了時にアクティブゲームから削除
        if channel_id in self.active_games:
            del self.active_games[channel_id]

    @app_commands.command(name='tictactoe', description='マルバツゲーム（TicTacToe）を開始します')
    @app_commands.describe(opponent='対戦相手のメンション')
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.User):
        """マルバツゲーム開始"""
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

            game = TicTacToeGame(interaction.user, opponent)
            self.active_games[interaction.channel_id] = game

            embed = discord.Embed(
                title="❌⭕ マルバツゲーム",
                description=f"{interaction.user.mention} (❌) vs {opponent.mention} (⭕)\n\n{game.get_board_display()}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"次のターン: {interaction.user.name} (❌)")

            view = TicTacToeView(game)
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # ゲームループ
            await self.tictactoe_game_loop(msg, game, view, interaction.channel_id)

        except Exception as e:
            error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
            logger.error(f"Error in tictactoe command: {error_message}")
            await send_error_to_discord(
                self.bot,
                "マルバツゲームコマンドエラー",
                error_message,
                "コマンドエラー"
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=create_error_embed("マルバツゲームエラー", str(e)), ephemeral=True)

    async def tictactoe_game_loop(self, message: discord.Message, game: TicTacToeGame, view: TicTacToeView, channel_id: int):
        """マルバツゲームループ"""
        while not game.game_over and not view.game_over:
            try:
                await asyncio.sleep(0.5)

                # 勝者判定（既に勝利状態）
                if game.game_over:
                    winner = game.player1 if game.winner == TicTacToeGame.X else game.player2
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
                    current_player = game.player1 if game.current_player == TicTacToeGame.X else game.player2
                    emoji = "❌" if game.current_player == TicTacToeGame.X else "⭕"

                    embed = discord.Embed(
                        title="❌⭕ マルバツゲーム",
                        description=f"{game.player1.mention} (❌) vs {game.player2.mention} (⭕)\n\n{game.get_board_display()}",
                        color=discord.Color.blue(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text=f"次のターン: {current_player.name} ({emoji})")
                    await message.edit(embed=embed, view=view)

            except Exception as e:
                error_message = f"{str(e)}\n\n```\n{traceback.format_exc()}\n```"
                logger.error(f"Error in tictactoe game loop: {error_message}")
                await send_error_to_discord(
                    self.bot,
                    "マルバツゲームループエラー",
                    error_message,
                    "ゲームエラー"
                )
                break

        # ゲーム終了時にアクティブゲームから削除
        if channel_id in self.active_games:
            del self.active_games[channel_id]

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


class OthelloGame:
    """オセロ/リバーシゲーム管理クラス"""

    ROWS = 8
    COLS = 8
    EMPTY = 0
    BLACK = 1
    WHITE = 2

    EMPTY_EMOJI = "⬜"
    BLACK_EMOJI = "⚫"
    WHITE_EMOJI = "⚪"

    def __init__(self, player1: discord.User, player2: discord.User):
        self.player1 = player1
        self.player2 = player2
        self.board = [[self.EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.current_player = self.BLACK
        self.game_over = False
        self.pass_count = 0

        # Initial setup: middle 4 pieces
        self.board[3][3] = self.WHITE
        self.board[3][4] = self.BLACK
        self.board[4][3] = self.BLACK
        self.board[4][4] = self.WHITE

    def get_valid_moves(self) -> list:
        """有効な手を取得"""
        valid_moves = []
        opponent = self.WHITE if self.current_player == self.BLACK else self.BLACK

        for row in range(self.ROWS):
            for col in range(self.COLS):
                if self.board[row][col] == self.EMPTY:
                    if self._has_valid_direction(row, col, self.current_player, opponent):
                        valid_moves.append((row, col))

        return valid_moves

    def _has_valid_direction(self, row: int, col: int, player: int, opponent: int) -> bool:
        """指定位置に有効な方向があるか確認"""
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

        for dr, dc in directions:
            r, c = row + dr, col + dc
            found_opponent = False

            while 0 <= r < self.ROWS and 0 <= c < self.COLS:
                if self.board[r][c] == opponent:
                    found_opponent = True
                elif self.board[r][c] == player and found_opponent:
                    return True
                else:
                    break
                r += dr
                c += dc

        return False

    def place_piece(self, row: int, col: int) -> bool:
        """ピースを配置して反転させる"""
        if self.board[row][col] != self.EMPTY:
            return False

        opponent = self.WHITE if self.current_player == self.BLACK else self.BLACK
        flipped = False

        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

        for dr, dc in directions:
            r, c = row + dr, col + dc
            flip_list = []

            while 0 <= r < self.ROWS and 0 <= c < self.COLS:
                if self.board[r][c] == opponent:
                    flip_list.append((r, c))
                elif self.board[r][c] == self.current_player:
                    if flip_list:
                        for fr, fc in flip_list:
                            self.board[fr][fc] = self.current_player
                        flipped = True
                    break
                else:
                    break
                r += dr
                c += dc

        if flipped:
            self.board[row][col] = self.current_player
        return flipped

    def switch_player(self):
        """プレイヤーを切り替え"""
        self.current_player = self.WHITE if self.current_player == self.BLACK else self.BLACK

    def check_game_over(self) -> bool:
        """ゲーム終了判定"""
        if not self.get_valid_moves():
            self.switch_player()
            if not self.get_valid_moves():
                self.game_over = True
                return True
            self.switch_player()
        self.pass_count = 0
        return False

    def get_score(self) -> tuple:
        """スコアを取得 (黒, 白)"""
        black_count = sum(row.count(self.BLACK) for row in self.board)
        white_count = sum(row.count(self.WHITE) for row in self.board)
        return (black_count, white_count)

    def get_board_display(self) -> str:
        """盤面を表示文字列に変換"""
        display = "  1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣\n"
        row_nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]

        for row in range(self.ROWS):
            display += row_nums[row]
            for col in range(self.COLS):
                cell = self.board[row][col]
                if cell == self.EMPTY:
                    display += self.EMPTY_EMOJI
                elif cell == self.BLACK:
                    display += self.BLACK_EMOJI
                else:
                    display += self.WHITE_EMOJI
            display += "\n"

        return display


class OthelloView(ui.View):
    """オセロ用ボタンビュー"""

    def __init__(self, game: 'OthelloGame', timeout: int = 300):
        super().__init__(timeout=timeout)
        self.game = game
        self.game_over = False

        # 8x8のボタンを作成
        for row in range(OthelloGame.ROWS):
            for col in range(OthelloGame.COLS):
                button = ui.Button(
                    label="　",
                    style=discord.ButtonStyle.gray,
                    custom_id=f"othello_{row}_{col}"
                )
                button.callback = self.make_move_callback(row, col)
                self.add_item(button)

    def make_move_callback(self, row: int, col: int):
        async def callback(interaction: discord.Interaction):
            current_player_user = self.game.player1 if self.game.current_player == OthelloGame.BLACK else self.game.player2

            if interaction.user.id != current_player_user.id:
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

            # 有効な手か確認
            valid_moves = self.game.get_valid_moves()
            if (row, col) not in valid_moves:
                await interaction.response.send_message(
                    "その位置には置けません",
                    ephemeral=True
                )
                return

            self.game.place_piece(row, col)
            self.game.switch_player()
            await interaction.response.defer()

        return callback

    async def on_timeout(self):
        self.game_over = True


class TicTacToeGame:
    """マルバツゲーム（TicTacToe）管理クラス"""

    ROWS = 3
    COLS = 3
    EMPTY = 0
    X = 1
    O = 2

    EMPTY_EMOJI = "⬜"
    X_EMOJI = "❌"
    O_EMOJI = "⭕"

    BUTTON_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

    def __init__(self, player1: discord.User, player2: discord.User):
        self.player1 = player1
        self.player2 = player2
        self.board = [self.EMPTY] * 9
        self.current_player = self.X
        self.game_over = False
        self.winner = None

    def make_move(self, position: int) -> bool:
        """位置にマークを配置"""
        if position < 0 or position >= 9 or self.board[position] != self.EMPTY:
            return False

        self.board[position] = self.current_player
        return True

    def check_winner(self) -> bool:
        """勝者判定"""
        winning_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # 行
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # 列
            [0, 4, 8], [2, 4, 6]              # 対角線
        ]

        for combo in winning_combinations:
            if (self.board[combo[0]] != self.EMPTY and
                self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]]):
                self.winner = self.board[combo[0]]
                return True

        return False

    def is_board_full(self) -> bool:
        """盤面が満杯か判定"""
        return self.EMPTY not in self.board

    def switch_player(self):
        """プレイヤーを切り替え"""
        self.current_player = self.O if self.current_player == self.X else self.X

    def get_board_display(self) -> str:
        """盤面を表示文字列に変換"""
        display = ""
        for i in range(self.ROWS):
            for j in range(self.COLS):
                cell = self.board[i * self.COLS + j]
                if cell == self.EMPTY:
                    display += self.BUTTON_EMOJIS[i * self.COLS + j]
                elif cell == self.X:
                    display += self.X_EMOJI
                else:
                    display += self.O_EMOJI
            display += "\n"

        return display


class TicTacToeView(ui.View):
    """マルバツゲーム用ボタンビュー"""

    def __init__(self, game: 'TicTacToeGame', timeout: int = 300):
        super().__init__(timeout=timeout)
        self.game = game
        self.game_over = False

        # 9個のボタンを作成
        for i in range(9):
            button = ui.Button(
                label=TicTacToeGame.BUTTON_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                custom_id=f"tictactoe_{i}"
            )
            button.callback = self.make_move_callback(i)
            self.add_item(button)

    def make_move_callback(self, position: int):
        async def callback(interaction: discord.Interaction):
            current_player_user = self.game.player1 if self.game.current_player == TicTacToeGame.X else self.game.player2

            if interaction.user.id != current_player_user.id:
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

            if not self.game.make_move(position):
                await interaction.response.send_message(
                    "その位置は既に使用されています",
                    ephemeral=True
                )
                return

            if self.game.check_winner():
                self.game.game_over = True
                self.game_over = True
            else:
                self.game.switch_player()

            await interaction.response.defer()

        return callback

    async def on_timeout(self):
        self.game_over = True


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
