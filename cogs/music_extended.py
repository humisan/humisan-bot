"""
拡張音楽機能 (統計、歌詞、推奨、共有、24/7再生)
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import base64
import json
import os
from dotenv import load_dotenv
from utils.database import get_database
from utils.logger import setup_logger
from utils.helpers import create_error_embed, create_success_embed

logger = setup_logger(__name__)

# 環境変数を読み込む
load_dotenv()
GENIUS_API_TOKEN = os.getenv('GENIUS_API_TOKEN')

# Genius APIの初期化（トークンがある場合）
try:
    if GENIUS_API_TOKEN and GENIUS_API_TOKEN != 'your_genius_token_here':
        from lyricsgenius import Genius
        genius = Genius(GENIUS_API_TOKEN, timeout=10, retries=3)
        LYRICS_AVAILABLE = True
    else:
        genius = None
        LYRICS_AVAILABLE = False
        logger.warning("Genius API token not configured - lyrics feature disabled")
except ImportError:
    genius = None
    LYRICS_AVAILABLE = False
    logger.warning("lyricsgenius not installed - install with: pip install lyricsgenius")

# 24/7自動再生セッションの管理
autoplay_sessions: Dict[int, dict] = {}  # guild_id -> autoplay info


class MusicExtended(commands.Cog):
    """拡張音楽機能 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_database()
        self.autoplay_loop.start()
        logger.info("MusicExtended Cog initialized")

    # ==================== /stats コマンド ====================

    @app_commands.command(
        name="stats",
        description="あなたの再生統計を表示します",
    )
    async def stats(self, interaction: discord.Interaction):
        """ユーザーの再生統計を表示"""
        try:
            guild_id = str(interaction.guild_id)
            user_id = str(interaction.user.id)

            stats = self.db.get_user_stats(guild_id, user_id)

            if not stats or stats['total_plays'] == 0:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "統計情報がありません",
                        "まだ曲を再生していません"
                    ),
                    ephemeral=True
                )
                return

            # 再生時間をフォーマット
            total_minutes = stats['total_playtime'] // 60
            hours = total_minutes // 60
            minutes = total_minutes % 60

            embed = discord.Embed(
                title="📊 あなたの再生統計",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="総再生数",
                value=f"**{stats['total_plays']}** 曲",
                inline=True
            )
            embed.add_field(
                name="総再生時間",
                value=f"**{hours}時間 {minutes}分**",
                inline=True
            )
            if stats['favorite_genre']:
                embed.add_field(
                    name="好きなジャンル",
                    value=f"**{stats['favorite_genre']}**",
                    inline=True
                )
            if stats['last_played_at']:
                try:
                    last_played = datetime.fromisoformat(stats['last_played_at'])
                    embed.add_field(
                        name="最後に再生した曲",
                        value=f"<t:{int(last_played.timestamp())}:R>",
                        inline=False
                    )
                except:
                    pass

            # トップ曲を取得
            top_songs = self.db.get_top_songs(guild_id, limit=5, user_id=user_id)
            if top_songs:
                top_list = "\n".join(
                    [f"{i+1}. **{song['title']}** ({song['play_count']}回)" for i, song in enumerate(top_songs)]
                )
                embed.add_field(
                    name="🎵 トップ5曲",
                    value=top_list,
                    inline=False
                )

            embed.set_footer(text=f"ユーザー: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)
            logger.info(f"Stats command executed for {interaction.user.name}")

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("統計の取得に失敗しました", str(e)),
                ephemeral=True
            )

    # ==================== /lyrics コマンド ====================

    @app_commands.command(
        name="lyrics",
        description="曲の歌詞を表示します",
    )
    @app_commands.describe(
        title="曲のタイトル",
        artist="アーティスト名（オプション）"
    )
    async def lyrics(
        self,
        interaction: discord.Interaction,
        title: str,
        artist: Optional[str] = None
    ):
        """曲の歌詞を表示"""
        if not LYRICS_AVAILABLE:
            await interaction.response.send_message(
                embed=create_error_embed(
                    "機能が利用できません",
                    "Genius API トークンが設定されていません。\n"
                    ".env ファイルに `GENIUS_API_TOKEN` を設定してください。\n\n"
                    "取得方法: https://genius.com/api-clients"
                ),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            logger.info(f"Fetching lyrics for: {title} by {artist or 'Unknown'}")

            # 歌詞を検索（非同期で実行）
            loop = asyncio.get_event_loop()
            song = await loop.run_in_executor(
                None,
                lambda: genius.search_song(title, artist)
            )

            if not song:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "歌詞が見つかりません",
                        f"「{title}」の歌詞が見つかりませんでした。"
                    )
                )
                return

            # 歌詞が長い場合は分割
            lyrics_text = song.lyrics
            if not lyrics_text:
                await interaction.followup.send(
                    embed=create_error_embed(
                        "歌詞が利用できません",
                        f"「{song.title}」の歌詞が利用できません。"
                    )
                )
                return

            # 歌詞を分割（Discord の メッセージ文字数制限: 2000文字）
            chunks = []
            current_chunk = ""

            for line in lyrics_text.split('\n'):
                if len(current_chunk) + len(line) + 1 > 1900:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line + '\n'
                else:
                    current_chunk += line + '\n'

            if current_chunk:
                chunks.append(current_chunk)

            # 歌詞を送信（最初のEmbedは情報付き）
            embed = discord.Embed(
                title=f"🎵 {song.title}",
                description=f"**アーティスト**: {song.artist}\n\n```\n{chunks[0]}\n```",
                color=discord.Color.blue(),
                url=song.url
            )
            embed.set_footer(text="Powered by Genius")
            await interaction.followup.send(embed=embed)

            # 残りの歌詞を送信
            for chunk in chunks[1:]:
                embed = discord.Embed(
                    description=f"```\n{chunk}\n```",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)

            logger.info(f"Lyrics sent for: {song.title}")

        except Exception as e:
            logger.error(f"Error fetching lyrics: {e}")
            await interaction.followup.send(
                embed=create_error_embed(
                    "エラーが発生しました",
                    f"歌詞の取得に失敗しました: {str(e)}"
                )
            )

    # ==================== /recommend コマンド ====================

    @app_commands.command(
        name="recommend",
        description="再生履歴から似たジャンルの曲を推奨します",
    )
    async def recommend(self, interaction: discord.Interaction):
        """推奨曲を提案"""
        try:
            guild_id = str(interaction.guild_id)
            user_id = str(interaction.user.id)

            # ユーザーの再生履歴からジャンルを取得
            genres = self.db.get_genre_history(guild_id, user_id, limit=20)

            if not genres:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "推奨情報がありません",
                        "再生履歴がまだありません。\n"
                        "いくつか曲を再生してから試してください。"
                    ),
                    ephemeral=True
                )
                return

            # 最も再生されたジャンルを取得
            favorite_genre = max(set(genres), key=genres.count) if genres else None

            embed = discord.Embed(
                title="🎯 推奨曲",
                color=discord.Color.green()
            )

            if favorite_genre:
                embed.add_field(
                    name="あなたが好きなジャンル",
                    value=f"**{favorite_genre}**",
                    inline=False
                )
                embed.add_field(
                    name="推奨",
                    value=f"{favorite_genre} のジャンルの曲を検索してみてください！\n"
                          f"YouTube や Spotify で `{favorite_genre}` で検索すると、\n"
                          f"あなたの好みに合った曲が見つかるかもしれません。",
                    inline=False
                )
            else:
                embed.add_field(
                    name="ジャンル情報",
                    value="再生履歴からジャンル情報が取得できませんでした。",
                    inline=False
                )

            # トップ曲も表示
            top_songs = self.db.get_top_songs(guild_id, limit=3, user_id=user_id)
            if top_songs:
                similar_songs = "\n".join(
                    [f"• {song['title']}" for song in top_songs]
                )
                embed.add_field(
                    name="あなたのお気に入り",
                    value=similar_songs,
                    inline=False
                )

            embed.set_footer(text="新しい曲を探してみてください！")
            await interaction.response.send_message(embed=embed)
            logger.info(f"Recommend command executed for {interaction.user.name}")

        except Exception as e:
            logger.error(f"Error in recommend command: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("推奨の取得に失敗しました", str(e)),
                ephemeral=True
            )

    # ==================== /share-playlist コマンド ====================

    @app_commands.command(
        name="share_playlist",
        description="プレイリストを共有できる形式でエンコードします",
    )
    @app_commands.describe(playlist_name="共有するプレイリスト名")
    async def share_playlist(self, interaction: discord.Interaction, playlist_name: str):
        """プレイリストを共有"""
        try:
            guild_id = str(interaction.guild_id)

            # プレイリストを取得
            playlist = self.db.get_playlist(guild_id, playlist_name)

            if not playlist:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "プレイリストが見つかりません",
                        f"「{playlist_name}」というプレイリストが見つかりません。"
                    ),
                    ephemeral=True
                )
                return

            # プレイリスト内の曲を取得
            songs = self.db.get_playlist_songs(playlist['id'])

            if not songs:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        "プレイリストが空です",
                        f"「{playlist_name}」に曲が含まれていません。"
                    ),
                    ephemeral=True
                )
                return

            # プレイリストをJSONでエンコード
            playlist_data = {
                'name': playlist['name'],
                'created_by': playlist['created_by'],
                'songs': [
                    {
                        'title': song['title'],
                        'url': song['url'],
                        'duration': song['duration']
                    }
                    for song in songs
                ]
            }

            # Base64でエンコード
            json_str = json.dumps(playlist_data, ensure_ascii=False)
            encoded = base64.b64encode(json_str.encode()).decode()

            # シェアコードを生成
            share_code = encoded[:50] + "..." if len(encoded) > 50 else encoded

            embed = discord.Embed(
                title="📤 プレイリスト共有",
                color=discord.Color.purple()
            )
            embed.add_field(
                name="プレイリスト名",
                value=f"**{playlist['name']}**",
                inline=False
            )
            embed.add_field(
                name="曲数",
                value=f"**{len(songs)}** 曲",
                inline=True
            )
            embed.add_field(
                name="作成者",
                value=f"**{playlist['created_by']}**",
                inline=True
            )
            embed.add_field(
                name="シェアコード",
                value=f"```\n{encoded}\n```",
                inline=False
            )
            embed.set_footer(text="このコードを他のユーザーに共有すると、プレイリストがインポートできます。")

            await interaction.response.send_message(embed=embed, ephemeral=False)
            logger.info(f"Playlist {playlist_name} shared by {interaction.user.name}")

        except Exception as e:
            logger.error(f"Error in share_playlist command: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("共有に失敗しました", str(e)),
                ephemeral=True
            )

    # ==================== /autoplay コマンド ====================

    @app_commands.command(
        name="autoplay",
        description="24/7自動再生モードを切り替えます",
    )
    async def autoplay(self, interaction: discord.Interaction):
        """24/7自動再生を切り替え"""
        try:
            guild_id = interaction.guild_id

            if guild_id in autoplay_sessions:
                # 自動再生を停止
                autoplay_sessions[guild_id]['enabled'] = False
                del autoplay_sessions[guild_id]
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "自動再生停止",
                        "24/7自動再生モードを停止しました。"
                    )
                )
                logger.info(f"Autoplay disabled for guild {guild_id}")
            else:
                # 自動再生を開始
                autoplay_sessions[guild_id] = {
                    'enabled': True,
                    'started_at': datetime.now()
                }
                await interaction.response.send_message(
                    embed=create_success_embed(
                        "自動再生開始",
                        "24/7自動再生モードを開始しました。\n"
                        "キューが空になると自動的に曲が追加されます。"
                    )
                )
                logger.info(f"Autoplay enabled for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error in autoplay command: {e}")
            await interaction.response.send_message(
                embed=create_error_embed("エラーが発生しました", str(e)),
                ephemeral=True
            )

    # ==================== バックグラウンドタスク ====================

    @tasks.loop(minutes=1)
    async def autoplay_loop(self):
        """24/7自動再生のバックグラウンドループ"""
        try:
            # Music Cog を取得
            music_cog = self.bot.get_cog('Music')
            if not music_cog:
                logger.warning("Music Cog not found for autoplay")
                return

            for guild_id, session in list(autoplay_sessions.items()):
                if not session.get('enabled'):
                    continue

                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logger.debug(f"Guild {guild_id} not found")
                        continue

                    # voice_client を取得
                    voice_client = guild.voice_client
                    if not voice_client or not voice_client.is_connected():
                        logger.debug(f"Bot not connected to voice in guild {guild_id}")
                        continue

                    # キューを取得
                    queue = music_cog.get_queue(guild_id)

                    # キューが空かつ何も再生されていない場合、曲を追加
                    if queue.is_empty() and not voice_client.is_playing():
                        logger.info(f"Autoplay: Queue is empty in guild {guild_id}, fetching songs...")

                        # music_history から最近の曲を取得（ランダムサンプリング）
                        recent_songs = self._get_random_songs_from_history(str(guild_id), limit=5)

                        if recent_songs:
                            for song in recent_songs:
                                # song オブジェクトを作成
                                song_obj = {
                                    'title': song['title'],
                                    'url': song['url'],
                                    'webpage_url': song['url'],
                                    'duration': song.get('duration'),
                                    'requester': guild.me,  # ボット自身をリクエスター扱い
                                    'thumbnail': None
                                }
                                queue.add(song_obj)
                                logger.info(f"Autoplay: Added '{song['title']}' to queue")

                            # 最初の曲を再生
                            if queue.current is None and queue.queue:
                                next_song = queue.queue.pop(0)
                                queue.current = next_song
                                queue.start_time = time.time()

                                try:
                                    from cogs.music import YTDLSource
                                    player = await YTDLSource.from_url(next_song['webpage_url'], loop=self.bot.loop, stream=True)
                                    voice_client.play(player, after=lambda e: music_cog.play_next(guild))
                                    logger.info(f"Autoplay: Started playing '{next_song['title']}'")
                                except Exception as e:
                                    logger.error(f"Autoplay: Error playing song: {str(e)}")
                        else:
                            logger.debug(f"Autoplay: No songs found in history for guild {guild_id}")

                except Exception as e:
                    logger.error(f"Autoplay error for guild {guild_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in autoplay loop: {e}")

    def _get_random_songs_from_history(self, guild_id: str, limit: int = 5) -> List[Dict]:
        """再生履歴からランダムに曲を取得"""
        try:
            import random
            cursor = self.db.conn.cursor()
            cursor.execute('''
                SELECT DISTINCT title, url, duration FROM music_history
                WHERE guild_id = ?
                ORDER BY RANDOM()
                LIMIT ?
            ''', (guild_id, limit * 2))  # 多めに取得して重複を避ける

            rows = cursor.fetchall()
            songs = []
            seen_urls = set()

            for row in rows:
                url = row[1]
                if url not in seen_urls:
                    songs.append({
                        'title': row[0],
                        'url': url,
                        'duration': row[2]
                    })
                    seen_urls.add(url)
                    if len(songs) >= limit:
                        break

            return songs
        except Exception as e:
            logger.error(f"Error getting songs from history: {str(e)}")
            return []

    @autoplay_loop.before_loop
    async def before_autoplay_loop(self):
        """ループ開始前の処理"""
        await self.bot.wait_until_ready()
        logger.info("Autoplay background loop started")

    def cog_unload(self):
        """Cog アンロード時の処理"""
        self.autoplay_loop.cancel()
        logger.info("MusicExtended Cog unloaded")


async def setup(bot: commands.Bot):
    """Cog をボットに登録"""
    await bot.add_cog(MusicExtended(bot))
    logger.info("MusicExtended Cog loaded")
