import discord
from discord.ext import commands, tasks
from discord import app_commands
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
from utils.database import get_database
import yt_dlp
import asyncio
from typing import Dict, List
import json
import os
import random
from enum import Enum
import time
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger(__name__)

# YouTube クッキーパス（オプション）
YOUTUBE_COOKIES_PATH = os.getenv('YOUTUBE_COOKIES_PATH')

# yt-dlpの設定
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'socket_timeout': 30,  # タイムアウト時間（秒）
    'http_headers': {  # ブラウザのようなヘッダーを追加
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
    },
    'extract_flat': 'in_playlist',  # プレイリストの動画IDを高速に取得
    'playlistend': 25,  # スラッシュコマンドで最初の25曲まで取得
    # YouTube の Bot 検出対策
    'youtube_include_dash_manifest': False,
    'quiet': True,
    'no_warnings': True,
    'skip_unavailable_fragments': True,
}

# YouTube クッキーが設定されている場合は追加
if YOUTUBE_COOKIES_PATH and os.path.exists(YOUTUBE_COOKIES_PATH):
    YTDL_OPTIONS['cookiefile'] = YOUTUBE_COOKIES_PATH
    logger.info(f"YouTube cookies loaded from: {YOUTUBE_COOKIES_PATH}")

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class RepeatMode(Enum):
    """リピートモード"""
    OFF = 0
    ONE = 1  # 1曲リピート
    ALL = 2  # 全曲リピート


class YTDLSource(discord.PCMVolumeTransformer):
    """YouTube音源クラス"""

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.webpage_url = data.get('webpage_url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        """URLから音源を作成"""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)


class MusicQueue:
    """音楽キュークラス"""

    def __init__(self):
        self.queue: List[Dict] = []
        self.current: Dict = None
        self.repeat_mode = RepeatMode.OFF
        self.shuffle = False
        self.history: List[Dict] = []
        self.start_time = None
        self.notification_channel_id: int = None  # /play が実行されたチャネル ID

    def add(self, song: Dict):
        """曲をキューに追加"""
        self.queue.append(song)

    def next(self):
        """次の曲を取得"""
        # リピート1曲モード
        if self.repeat_mode == RepeatMode.ONE and self.current:
            return self.current

        # 履歴に追加
        if self.current:
            self.history.append(self.current)

        if self.queue:
            if self.shuffle:
                self.current = self.queue.pop(random.randint(0, len(self.queue) - 1))
            else:
                self.current = self.queue.pop(0)
            self.start_time = time.time()
            return self.current

        # リピート全曲モード
        if self.repeat_mode == RepeatMode.ALL and self.history:
            self.queue = self.history.copy()
            self.history.clear()
            self.current = self.queue.pop(0)
            self.start_time = time.time()
            return self.current

        return None

    def clear(self):
        """キューをクリア"""
        self.queue.clear()
        self.current = None
        self.history.clear()
        self.start_time = None

    def is_empty(self):
        """キューが空か確認"""
        return len(self.queue) == 0

    def get_position(self):
        """現在の再生位置（秒）を取得"""
        if self.start_time:
            return int(time.time() - self.start_time)
        return 0


class Music(commands.Cog):
    """音楽再生機能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_database()
        self.queues: Dict[int, MusicQueue] = {}
        self.favorites_file = 'favorites.json'
        self.favorites = self.load_favorites()
        self.playlists_file = 'playlists.json'
        self.playlists = self.load_playlists()
        self.skip_votes: Dict[int, set] = {}  # guild_id -> {user_ids}
        self.idle_timers: Dict[int, float] = {}  # guild_id -> last_play_time

        # Start background tasks
        try:
            if not self.auto_disconnect_task.is_running():
                self.auto_disconnect_task.start()
        except Exception as e:
            logger.error(f"Failed to start auto_disconnect_task: {str(e)}")

    def load_favorites(self):
        """お気に入りを読み込む"""
        if os.path.exists(self.favorites_file):
            with open(self.favorites_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_favorites(self):
        """お気に入りを保存"""
        with open(self.favorites_file, 'w', encoding='utf-8') as f:
            json.dump(self.favorites, f, ensure_ascii=False, indent=2)

    def load_playlists(self):
        """プレイリストを読み込む"""
        if os.path.exists(self.playlists_file):
            with open(self.playlists_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_queue_file(self, guild_id: int) -> str:
        """ギルドのキューファイルパスを取得"""
        return f'data/queue_{guild_id}.json'

    def save_queue(self, guild_id: int):
        """キューをJSONに保存"""
        try:
            queue = self.get_queue(guild_id)
            queue_data = {
                'current': None,
                'queue': [],
                'repeat_mode': queue.repeat_mode.value,
                'shuffle': queue.shuffle
            }

            # 現在再生中の曲を保存
            if queue.current:
                queue_data['current'] = {
                    'title': queue.current.get('title'),
                    'webpage_url': queue.current.get('webpage_url'),
                    'duration': queue.current.get('duration')
                }

            # キュー内の曲を保存
            for song in queue.queue:
                queue_data['queue'].append({
                    'title': song.get('title'),
                    'webpage_url': song.get('webpage_url'),
                    'duration': song.get('duration')
                })

            queue_file = self.get_queue_file(guild_id)
            os.makedirs(os.path.dirname(queue_file), exist_ok=True)
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Queue saved for guild {guild_id} ({len(queue_data['queue'])} songs)")
        except Exception as e:
            logger.error(f"Error saving queue for guild {guild_id}: {str(e)}")

    def load_queue(self, guild_id: int):
        """JSONからキューを復元"""
        try:
            queue_file = self.get_queue_file(guild_id)
            if not os.path.exists(queue_file):
                logger.debug(f"No queue file found for guild {guild_id}")
                return

            with open(queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)

            queue = self.get_queue(guild_id)

            # キュー内の曲を復元
            for song_data in queue_data.get('queue', []):
                queue.add({
                    'title': song_data.get('title'),
                    'webpage_url': song_data.get('webpage_url'),
                    'duration': song_data.get('duration'),
                    'requester': None,  # リクエスター情報は復元不可
                    'thumbnail': None
                })

            # リピートモードとシャッフルを復元
            try:
                queue.repeat_mode = RepeatMode(queue_data.get('repeat_mode', 0))
            except:
                queue.repeat_mode = RepeatMode.OFF

            queue.shuffle = queue_data.get('shuffle', False)

            logger.info(f"Queue restored for guild {guild_id} ({len(queue.queue)} songs)")
        except Exception as e:
            logger.error(f"Error loading queue for guild {guild_id}: {str(e)}")

    def save_playlists(self):
        """プレイリストを保存"""
        with open(self.playlists_file, 'w', encoding='utf-8') as f:
            json.dump(self.playlists, f, ensure_ascii=False, indent=2)

    def get_queue(self, guild_id: int) -> MusicQueue:
        """ギルドのキューを取得"""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    def format_duration(self, seconds):
        """秒を MM:SS 形式に変換"""
        if not seconds:
            return "0:00"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    async def search_songs(self, query: str, limit: int = 5):
        """曲を検索"""
        loop = asyncio.get_event_loop()
        ydl_opts = YTDL_OPTIONS.copy()
        ydl_opts['quiet'] = True

        try:
            data = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(f"ytsearch{limit}:{query}", download=False)
            )
            entries = data.get('entries', [])

            # webpage_url を追加
            for entry in entries:
                if 'webpage_url' not in entry and entry.get('id'):
                    entry['webpage_url'] = f"https://www.youtube.com/watch?v={entry.get('id')}"

            return entries
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return []

    @app_commands.command(name='play', description='YouTube URL から曲を再生します')
    @app_commands.describe(url='YouTube の URL')
    async def play(self, interaction: discord.Interaction, url: str):
        """YouTube URL の曲を再生"""
        # URL バリデーション
        if not ('youtube.com' in url or 'youtu.be' in url):
            await interaction.response.send_message(
                embed=create_error_embed("YouTube URL を入力してください", "youtube.com または youtu.be のリンクをお願いします"),
                ephemeral=True
            )
            return

        # ギルドメンバーの情報を取得（非同期版）
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except Exception as e:
            logger.warning(f"Failed to fetch member: {e}")
            member = None

        logger.info(f"play command called by {interaction.user.name} with URL: {url}")

        # ボイスチャネル接続確認
        if not member or not member.voice or not member.voice.channel:
            logger.warning(f"User {interaction.user.name} is not connected to voice channel")
            await interaction.response.send_message(
                embed=create_error_embed("ボイスチャネルに接続してください"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # 実際の再生処理
        await self._perform_play(interaction, url)

    async def _perform_play(self, interaction: discord.Interaction, url: str):
        """実際の再生処理（play コマンドと SearchView から共通で使用）"""
        # ギルドメンバーの情報を取得（非同期版）
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except Exception as e:
            logger.warning(f"Failed to fetch member: {e}")
            member = None

        if not member or not member.voice or not member.voice.channel:
            await interaction.followup.send(
                embed=create_error_embed("ボイスチャネルに接続してください"),
                ephemeral=True
            )
            return

        voice_channel = member.voice.channel
        voice_client = interaction.guild.voice_client

        # ボイスチャネルに接続
        if not voice_client:
            voice_client = await voice_channel.connect()
            # ボットをデフォン状態に設定（常にスピーカーミュート）
            try:
                await interaction.guild.me.edit(deafen=True)
            except discord.Forbidden:
                logger.warning("Failed to deafen bot: Missing 'Manage Members' permission")
            except Exception as e:
                logger.warning(f"Failed to deafen bot: {str(e)}")

        try:
            # 曲情報を取得（タイムアウト付き）
            loop = asyncio.get_event_loop()
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False)),
                    timeout=120  # 120秒でタイムアウト（プレイリスト対応）
                )
            except asyncio.TimeoutError:
                logger.error(f"Timeout while extracting video info for URL: {url}")
                await interaction.followup.send(
                    embed=create_error_embed(
                        "曲の取得がタイムアウトしました",
                        "YouTube から情報を取得するのに時間がかかりすぎています。別の曲を試してください。"
                    )
                )
                return

            # プレイリストまたは単一の曲を処理
            songs_to_add = []

            # 曲数を取得してログに出力
            if 'entries' in data:
                total_songs = len(data.get('entries', []))
                logger.info(f"Playlist detected: Fetched {total_songs} songs (max 25 songs per playlist)")
            else:
                logger.info(f"Single song detected: {data.get('title', 'Unknown')}")

            if 'entries' in data:
                # プレイリストの場合（最大25曲まで）
                max_songs = 25
                total_entries = len(data.get('entries', []))

                for i, entry in enumerate(data['entries']):
                    # 25曲に達したら終了
                    if len(songs_to_add) >= max_songs:
                        break

                    if entry:
                        # extract_flat を使用している場合、webpage_url が None になる可能性があるので、id から URL を構築
                        webpage_url = entry.get('webpage_url')
                        if not webpage_url and entry.get('id'):
                            webpage_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                        if webpage_url:  # URL が取得できた場合のみ追加
                            song = {
                                'url': entry.get('url'),
                                'title': entry.get('title', 'Unknown'),
                                'duration': entry.get('duration', 0),
                                'thumbnail': entry.get('thumbnail'),
                                'requester': interaction.user,
                                'webpage_url': webpage_url
                            }
                            songs_to_add.append(song)

                if not songs_to_add:
                    await interaction.followup.send(
                        embed=create_error_embed("プレイリストが空です")
                    )
                    return

                # 実際に取得された曲数をログに表示
                logger.info(f"Added {len(songs_to_add)} songs to queue from playlist")
            else:
                # 単一の曲の場合
                webpage_url = data.get('webpage_url')
                if not webpage_url and data.get('id'):
                    webpage_url = f"https://www.youtube.com/watch?v={data.get('id')}"

                song = {
                    'url': data.get('url'),
                    'title': data['title'],
                    'duration': data.get('duration', 0),
                    'thumbnail': data.get('thumbnail'),
                    'requester': interaction.user,
                    'webpage_url': webpage_url
                }
                songs_to_add.append(song)

            queue = self.get_queue(interaction.guild.id)
            first_song = songs_to_add[0]

            # チャネル ID を保存（通知用）
            if queue.notification_channel_id is None:
                queue.notification_channel_id = interaction.channel.id

            # キューに曲が入っていない場合のみ即座に再生
            if queue.current is None and not voice_client.is_playing():
                player = await YTDLSource.from_url(first_song['webpage_url'], loop=self.bot.loop, stream=True)
                voice_client.play(player, after=lambda e: self.play_next(interaction.guild))
                queue.current = first_song
                queue.start_time = time.time()

                # 再生履歴に記録
                try:
                    self.db.record_music_history(
                        user_id=str(interaction.user.id),
                        title=first_song['title'],
                        url=first_song['webpage_url'],
                        genre=None,  # ジャンル情報はYouTubeから自動取得不可のため None
                        duration=first_song.get('duration')
                    )
                except Exception as e:
                    logger.warning(f"Failed to record music history: {str(e)}")

                # 残りの曲をキューに追加
                for song in songs_to_add[1:]:
                    queue.add(song)

                embed = discord.Embed(
                    title="🎵 再生中",
                    description=f"[{first_song['title']}]({first_song['webpage_url']})",
                    color=discord.Color.blue()
                )
                if first_song['thumbnail']:
                    embed.set_thumbnail(url=first_song['thumbnail'])
                embed.add_field(name="リクエスト", value=interaction.user.mention, inline=False)
                if first_song['duration']:
                    embed.add_field(name="再生時間", value=self.format_duration(first_song['duration']), inline=False)

                if len(songs_to_add) > 1:
                    embed.add_field(name="キューに追加", value=f"{len(songs_to_add) - 1} 曲", inline=False)

                await interaction.followup.send(embed=embed, view=MusicControlView(self, interaction.guild.id))
            else:
                # キューに追加
                for song in songs_to_add:
                    queue.add(song)

                embed = discord.Embed(
                    title="➕ キューに追加",
                    description=f"[{first_song['title']}]({first_song['webpage_url']})",
                    color=discord.Color.green()
                )
                queue_position = len(queue.queue) - len(songs_to_add) + 1
                embed.add_field(name="キューの位置", value=f"#{queue_position} ～ #{len(queue.queue)}", inline=False)
                embed.add_field(name="追加曲数", value=f"{len(songs_to_add)} 曲", inline=False)

                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error playing music: {str(e)}")
            await interaction.followup.send(
                embed=create_error_embed("音楽の再生に失敗しました", str(e))
            )

    async def _perform_play_prefix(self, ctx: commands.Context, url: str):
        """プリフィックスコマンド用の再生処理（ctx を使用）"""
        try:
            voice_channel = ctx.author.voice.channel
            voice_client = ctx.guild.voice_client

            # ボイスチャネルに接続
            if not voice_client:
                voice_client = await voice_channel.connect()
                # ボットをデフォン状態に設定
                try:
                    await ctx.guild.me.edit(deafen=True)
                except discord.Forbidden:
                    logger.warning("Failed to deafen bot: Missing 'Manage Members' permission")
                except Exception as e:
                    logger.warning(f"Failed to deafen bot: {str(e)}")

            try:
                # 曲情報を取得
                loop = asyncio.get_event_loop()
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False)),
                        timeout=120
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Timeout while extracting video info for URL: {url}")
                    await ctx.send(embed=create_error_embed(
                        "曲の取得がタイムアウトしました",
                        "YouTube から情報を取得するのに時間がかかりすぎています。別の曲を試してください。"
                    ))
                    return

                # プレイリストまたは単一の曲を処理
                songs_to_add = []

                if 'entries' in data:
                    # プレイリスト処理
                    max_songs = 25
                    for i, entry in enumerate(data['entries']):
                        if len(songs_to_add) >= max_songs:
                            break
                        if entry:
                            webpage_url = entry.get('webpage_url')
                            if not webpage_url and entry.get('id'):
                                webpage_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                            if webpage_url:
                                song = {
                                    'url': entry.get('url'),
                                    'title': entry.get('title', 'Unknown'),
                                    'duration': entry.get('duration', 0),
                                    'thumbnail': entry.get('thumbnail'),
                                    'requester': ctx.author,
                                    'webpage_url': webpage_url
                                }
                                songs_to_add.append(song)

                    if not songs_to_add:
                        await ctx.send(embed=create_error_embed("プレイリストが空です"))
                        return
                else:
                    # 単一の曲
                    webpage_url = data.get('webpage_url')
                    if not webpage_url and data.get('id'):
                        webpage_url = f"https://www.youtube.com/watch?v={data.get('id')}"
                    song = {
                        'url': data.get('url'),
                        'title': data['title'],
                        'duration': data.get('duration', 0),
                        'thumbnail': data.get('thumbnail'),
                        'requester': ctx.author,
                        'webpage_url': webpage_url
                    }
                    songs_to_add.append(song)

                queue = self.get_queue(ctx.guild.id)
                first_song = songs_to_add[0]

                # チャネル ID を保存
                if queue.notification_channel_id is None:
                    queue.notification_channel_id = ctx.channel.id

                # キューに曲が入っていない場合のみ即座に再生
                if queue.current is None and not voice_client.is_playing():
                    player = await YTDLSource.from_url(first_song['webpage_url'], loop=self.bot.loop, stream=True)
                    voice_client.play(player, after=lambda e: self.play_next(ctx.guild))
                    queue.current = first_song
                    queue.start_time = time.time()

                    # 再生履歴に記録
                    try:
                        self.db.record_music_history(
                            user_id=str(ctx.author.id),
                            title=first_song['title'],
                            url=first_song['webpage_url'],
                            genre=None,
                            duration=first_song.get('duration')
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record music history: {str(e)}")

                    # 残りの曲をキューに追加
                    for song in songs_to_add[1:]:
                        queue.add(song)

                    embed = discord.Embed(
                        title="🎵 再生中",
                        description=f"[{first_song['title']}]({first_song['webpage_url']})",
                        color=discord.Color.blue()
                    )
                    if first_song['thumbnail']:
                        embed.set_thumbnail(url=first_song['thumbnail'])
                    embed.add_field(name="リクエスト", value=ctx.author.mention, inline=False)
                    if first_song['duration']:
                        embed.add_field(name="再生時間", value=self.format_duration(first_song['duration']), inline=False)
                    if len(songs_to_add) > 1:
                        embed.add_field(name="キューに追加", value=f"{len(songs_to_add) - 1} 曲", inline=False)

                    await ctx.send(embed=embed)
                else:
                    # キューに追加
                    for song in songs_to_add:
                        queue.add(song)

                    embed = discord.Embed(
                        title="➕ キューに追加",
                        description=f"[{first_song['title']}]({first_song['webpage_url']})",
                        color=discord.Color.green()
                    )
                    queue_position = len(queue.queue) - len(songs_to_add) + 1
                    embed.add_field(name="キューの位置", value=f"#{queue_position} ～ #{len(queue.queue)}", inline=False)
                    embed.add_field(name="追加曲数", value=f"{len(songs_to_add)} 曲", inline=False)

                    await ctx.send(embed=embed)

            except Exception as e:
                logger.error(f"Error playing music: {str(e)}")
                await ctx.send(embed=create_error_embed("音楽の再生に失敗しました", str(e)))

        except Exception as e:
            logger.error(f"Error in _perform_play_prefix: {str(e)}")
            await ctx.send(embed=create_error_embed("エラーが発生しました", str(e)))

    @app_commands.command(name='search', description='YouTube から曲を検索して再生します')
    @app_commands.describe(query='検索キーワード')
    async def search(self, interaction: discord.Interaction, query: str):
        """曲を検索して候補を表示"""
        # ギルドメンバーの情報を取得（非同期版）
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except Exception as e:
            logger.warning(f"Failed to fetch member: {e}")
            member = None

        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                embed=create_error_embed("ボイスチャネルに接続してください"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            songs = await self.search_songs(query, limit=20)

            if not songs:
                await interaction.followup.send(
                    embed=create_error_embed("曲が見つかりません")
                )
                return

            embed = discord.Embed(
                title="🔍 検索結果",
                description=f"「{query}」の検索結果（全 {len(songs)} 件）",
                color=discord.Color.blue()
            )

            # 最初のページの5曲を表示
            description = ""
            for i, song in enumerate(songs[:5], 1):
                title = song.get('title', 'Unknown')
                duration = self.format_duration(song.get('duration', 0))
                description += f"{i}. {title} ({duration})\n"

            embed.description += "\n" + description
            if len(songs) > 5:
                embed.set_footer(text="下のボタンをクリックして再生する曲を選択するか、「次へ」で更に検索結果を見てください")
            else:
                embed.set_footer(text="下のボタンをクリックして再生する曲を選択してください")

            # ボタンビューを作成
            view = SearchView(self, songs, interaction.user, query)
            await interaction.followup.send(embed=view.get_embed(), view=view)

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            await interaction.followup.send(
                embed=create_error_embed("検索に失敗しました", str(e))
            )

    @app_commands.command(name='repeat', description='リピートモードを変更します')
    async def repeat(self, interaction: discord.Interaction):
        """リピートモードを切り替え"""
        queue = self.get_queue(interaction.guild.id)

        if queue.repeat_mode == RepeatMode.OFF:
            queue.repeat_mode = RepeatMode.ONE
            mode_text = "1曲リピート"
        elif queue.repeat_mode == RepeatMode.ONE:
            queue.repeat_mode = RepeatMode.ALL
            mode_text = "全曲リピート"
        else:
            queue.repeat_mode = RepeatMode.OFF
            mode_text = "リピートOFF"

        embed = create_success_embed("🔁 リピートモード変更", f"リピートモード: **{mode_text}**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='shuffle', description='シャッフルモードを切り替えます')
    async def shuffle(self, interaction: discord.Interaction):
        """シャッフルモードを切り替え"""
        queue = self.get_queue(interaction.guild.id)
        queue.shuffle = not queue.shuffle

        status = "有効" if queue.shuffle else "無効"
        embed = create_success_embed("🔀 シャッフル", f"シャッフル: **{status}**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='nowplaying', description='現在再生中の曲と再生時間を表示します')
    async def nowplaying(self, interaction: discord.Interaction):
        """現在再生中の曲を表示"""
        queue = self.get_queue(interaction.guild.id)

        if not queue.current:
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の曲がありません"),
                ephemeral=True
            )
            return

        song = queue.current
        position = queue.get_position()

        embed = discord.Embed(
            title="🎵 現在再生中",
            description=f"[{song['title']}]({song['webpage_url']})",
            color=discord.Color.blue()
        )
        if song['thumbnail']:
            embed.set_thumbnail(url=song['thumbnail'])

        # プログレスバー
        if song['duration']:
            progress = int((position / song['duration']) * 20)
            progress_bar = "█" * progress + "░" * (20 - progress)
            embed.add_field(
                name="再生進行状況",
                value=f"`{progress_bar}`\n{self.format_duration(position)} / {self.format_duration(song['duration'])}",
                inline=False
            )
        else:
            embed.add_field(name="再生時間", value=self.format_duration(position), inline=False)

        embed.add_field(name="リクエスト", value=song['requester'].mention, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='favorite', description='現在再生中の曲をお気に入りに追加します')
    async def favorite(self, interaction: discord.Interaction):
        """曲をお気に入りに追加"""
        queue = self.get_queue(interaction.guild.id)

        if not queue.current:
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の曲がありません"),
                ephemeral=True
            )
            return

        song = queue.current
        user_id = str(interaction.user.id)

        if user_id not in self.favorites:
            self.favorites[user_id] = []

        # 重複チェック
        for fav in self.favorites[user_id]:
            if fav['url'] == song['url']:
                await interaction.response.send_message(
                    embed=create_error_embed("この曲は既にお気に入りです"),
                    ephemeral=True
                )
                return

        self.favorites[user_id].append({
            'title': song['title'],
            'url': song['url'],
            'webpage_url': song['webpage_url'],
            'duration': song['duration']
        })

        self.save_favorites()
        embed = create_success_embed("❤️ お気に入り追加", f"「{song['title']}」をお気に入りに追加しました")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='favorites', description='お気に入りリストを表示します')
    async def favorites(self, interaction: discord.Interaction):
        """お気に入りリストを表示"""
        user_id = str(interaction.user.id)

        if user_id not in self.favorites or not self.favorites[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed("お気に入りがありません"),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="❤️ お気に入りリスト",
            color=discord.Color.red()
        )

        for i, song in enumerate(self.favorites[user_id][:10], 1):
            duration = self.format_duration(song.get('duration', 0))
            embed.add_field(
                name=f"{i}. {song['title']}",
                value=f"({duration})",
                inline=False
            )

        if len(self.favorites[user_id]) > 10:
            embed.add_field(name="", value=f"... 他 {len(self.favorites[user_id]) - 10} 曲", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='pause', description='音楽を一時停止します')
    async def pause(self, interaction: discord.Interaction):
        """音楽を一時停止"""
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の音楽がありません"),
                ephemeral=True
            )
            return

        voice_client.pause()
        await interaction.response.send_message(embed=create_success_embed("⏸️ 一時停止", "音楽を一時停止しました"))

    @app_commands.command(name='resume', description='音楽を再開します')
    async def resume(self, interaction: discord.Interaction):
        """音楽を再開"""
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_paused():
            await interaction.response.send_message(
                embed=create_error_embed("一時停止中の音楽がありません"),
                ephemeral=True
            )
            return

        voice_client.resume()
        await interaction.response.send_message(embed=create_success_embed("▶️ 再開", "音楽を再開しました"))

    @app_commands.command(name='skip', description='現在の曲をスキップします（投票制）')
    async def skip(self, interaction: discord.Interaction):
        """曲をスキップ（投票制）"""
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の音楽がありません"),
                ephemeral=True
            )
            return

        guild_id = interaction.guild.id

        # ボイスチャネルのメンバー数を取得（ボット自身は除外）
        voice_channel = voice_client.channel
        human_members = [m for m in voice_channel.members if not m.bot]
        num_members = len(human_members)

        # 必要投票数を計算（メンバー数の過半数）
        required_votes = (num_members // 2) + 1

        # スキップ投票を初期化
        if guild_id not in self.skip_votes:
            self.skip_votes[guild_id] = set()

        # ユーザーが既に投票していないかチェック
        if interaction.user.id in self.skip_votes[guild_id]:
            await interaction.response.send_message(
                embed=create_error_embed("既に投票済みです", f"現在の投票: {len(self.skip_votes[guild_id])}/{required_votes}"),
                ephemeral=True
            )
            return

        # 投票を追加
        self.skip_votes[guild_id].add(interaction.user.id)
        current_votes = len(self.skip_votes[guild_id])

        # 投票数が必要数に達したかチェック
        if current_votes >= required_votes:
            # スキップ実行
            self.skip_votes[guild_id].clear()
            voice_client.stop()
            embed = discord.Embed(
                title="⏭️ スキップ",
                description="投票によって曲がスキップされました",
                color=discord.Color.green()
            )
            embed.add_field(name="投票数", value=f"{current_votes}/{required_votes}", inline=True)
            await interaction.response.send_message(embed=embed)
        else:
            # 投票待機中
            remaining_votes = required_votes - current_votes
            embed = discord.Embed(
                title="🗳️ スキップ投票",
                description=f"投票が記録されました",
                color=discord.Color.blue()
            )
            embed.add_field(name="現在の投票", value=f"{current_votes}/{required_votes}", inline=False)
            embed.add_field(name="必要な投票数", value=f"あと{remaining_votes}票", inline=False)
            embed.add_field(name="ボイスチャネルの人数", value=f"{num_members}人", inline=False)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name='stop', description='音楽を停止してキューをクリアします')
    async def stop(self, interaction: discord.Interaction):
        """音楽を停止"""
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await interaction.response.send_message(
                embed=create_error_embed("ボイスチャネルに接続していません"),
                ephemeral=True
            )
            return

        queue = self.get_queue(interaction.guild.id)
        queue.clear()

        voice_client.stop()
        await interaction.response.send_message(embed=create_success_embed("⏹️ 停止", "音楽を停止してキューをクリアしました"))

    @app_commands.command(name='queue', description='現在のキューを表示します')
    async def queue_command(self, interaction: discord.Interaction):
        """キューを表示"""
        queue = self.get_queue(interaction.guild.id)

        if not queue.current and queue.is_empty():
            await interaction.response.send_message(
                embed=create_error_embed("キューが空です"),
                ephemeral=True
            )
            return

        # キュー統計情報を計算
        total_duration = 0
        if queue.current and queue.current.get('duration'):
            total_duration += queue.current['duration']

        for song in queue.queue:
            if song.get('duration'):
                total_duration += song['duration']

        queue_count = len(queue.queue)
        total_songs = (1 if queue.current else 0) + queue_count

        # QueueView を作成
        view = QueueView(self, queue, total_duration, total_songs, interaction.user)
        embed = view.get_embed()

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name='leave', description='ボイスチャネルから退出します')
    async def leave(self, interaction: discord.Interaction):
        """ボイスチャネルから退出"""
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await interaction.response.send_message(
                embed=create_error_embed("ボイスチャネルに接続していません"),
                ephemeral=True
            )
            return

        queue = self.get_queue(interaction.guild.id)
        queue.clear()

        await voice_client.disconnect()
        await interaction.response.send_message(embed=create_success_embed("👋 退出", "ボイスチャネルから退出しました"))

    @app_commands.command(name='volume', description='音量を調整します')
    @app_commands.describe(volume='音量（0-100）')
    async def volume(self, interaction: discord.Interaction, volume: int):
        """音量を調整"""
        if volume < 0 or volume > 100:
            await interaction.response.send_message(
                embed=create_error_embed("音量は0〜100の間に設定してください"),
                ephemeral=True
            )
            return

        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の音楽がありません"),
                ephemeral=True
            )
            return

        voice_client.source.volume = volume / 100
        await interaction.response.send_message(
            embed=create_success_embed("🔊 音量変更", f"音量を {volume}% に設定しました")
        )

    def play_next(self, guild: discord.Guild):
        """次の曲を再生"""
        asyncio.run_coroutine_threadsafe(self._play_next_async(guild), self.bot.loop)

    async def _play_next_async(self, guild: discord.Guild):
        """次の曲を再生（非同期版）"""
        queue = self.get_queue(guild.id)
        voice_client = guild.voice_client

        # 次の曲への移動時にスキップ投票をリセット
        if guild.id in self.skip_votes:
            self.skip_votes[guild.id].clear()

        if not queue.is_empty() or queue.repeat_mode == RepeatMode.ALL:
            song = queue.next()
            if song:
                loop = asyncio.get_event_loop()

                try:
                    player = await YTDLSource.from_url(song['webpage_url'], loop=loop, stream=True)
                    voice_client.play(player, after=lambda e: self.play_next(guild))

                    # 再生履歴に記録（次の曲が再生される時）
                    try:
                        # 現在の曲をリクエストしたユーザーを取得
                        requester = song.get('requester')
                        if requester:
                            self.db.record_music_history(
                                user_id=str(requester.id),
                                title=song['title'],
                                url=song['webpage_url'],
                                genre=None,  # ジャンル情報はYouTubeから自動取得不可のため None
                                duration=song.get('duration')
                            )
                    except Exception as e:
                        logger.warning(f"Failed to record music history: {str(e)}")

                    # 通知チャネルに embed を送信
                    if queue.notification_channel_id:
                        channel = guild.get_channel(queue.notification_channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🎵 再生中",
                                description=f"[{song['title']}]({song['webpage_url']})",
                                color=discord.Color.blue()
                            )
                            if song.get('thumbnail'):
                                embed.set_thumbnail(url=song['thumbnail'])
                            if song.get('duration'):
                                embed.add_field(name="再生時間", value=self.format_duration(song['duration']), inline=False)
                            embed.add_field(name="リクエスト", value=song['requester'].mention, inline=False)
                            try:
                                await channel.send(embed=embed, view=MusicControlView(self, guild.id))
                            except Exception as e:
                                logger.error(f"Failed to send notification: {str(e)}")

                except Exception as e:
                    logger.error(f"Error playing next song: {str(e)}")
        else:
            # キューが空かつリピートモードが ALL でない場合
            # current をクリアして、新しい曲が追加される時に即座に再生できるようにする
            queue.current = None
            logger.debug(f"Queue emptied, cleared current for guild {guild.id}")

            # キューに曲が残っていて再生されていない場合は、再度 play_next を呼ぶ
            if not queue.is_empty() and not voice_client.is_playing():
                logger.info(f"Queue has songs but nothing is playing, scheduling next play for guild {guild.id}")
                await asyncio.sleep(0.5)  # 少し遅延させる
                await self._play_next_async(guild)

    # ==================== 自動切断機能 ====================

    @tasks.loop(minutes=1)
    async def auto_disconnect_task(self):
        """30分以上の無音時を検出して自動切断"""
        try:
            current_time = time.time()
            idle_threshold = 30 * 60  # 30分

            for guild in self.bot.guilds:
                try:
                    voice_client = guild.voice_client

                    # ボットがボイスチャネルに接続していない場合はスキップ
                    if not voice_client or not voice_client.is_connected():
                        if guild.id in self.idle_timers:
                            del self.idle_timers[guild.id]
                        continue

                    # 曲が再生されている場合、タイマーをリセット
                    if voice_client.is_playing():
                        self.idle_timers[guild.id] = current_time
                        continue

                    # 初めてアイドル状態を検出した場合、現在時刻を記録
                    if guild.id not in self.idle_timers:
                        self.idle_timers[guild.id] = current_time
                        logger.info(f"Guild {guild.name} ({guild.id}) started idle timer")
                        continue

                    # アイドル時間を計算
                    idle_time = current_time - self.idle_timers[guild.id]

                    # 30分以上アイドルの場合、自動切断
                    if idle_time >= idle_threshold:
                        queue = self.get_queue(guild.id)
                        queue.clear()
                        await voice_client.disconnect()
                        del self.idle_timers[guild.id]
                        logger.info(f"Auto-disconnected from guild {guild.name} ({guild.id}) after {idle_time / 60:.0f} minutes of idle")

                except Exception as e:
                    logger.error(f"Error checking idle timer for guild {guild.id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in auto_disconnect_task: {str(e)}")

    @auto_disconnect_task.before_loop
    async def before_auto_disconnect_task(self):
        """タスク開始前の処理"""
        await self.bot.wait_until_ready()
        logger.info("Auto-disconnect task started")

    # ==================== オートコンプリート関数 ====================

    async def playlist_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """プレイリスト名のオートコンプリート"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists:
            return []

        playlist_names = list(self.playlists[user_id].keys())

        # 現在の入力に基づいてフィルタリング
        matches = [
            name for name in playlist_names
            if name.lower().startswith(current.lower())
        ]

        # 最大25個まで返す（Discord の制限）
        return [
            app_commands.Choice(name=name, value=name)
            for name in matches[:25]
        ]

    # プレイリスト機能
    playlist_group = app_commands.Group(name='playlist', description='プレイリスト機能')

    @playlist_group.command(name='create', description='新規プレイリストを作成')
    @app_commands.describe(name='プレイリスト名')
    async def playlist_create(self, interaction: discord.Interaction, name: str):
        """プレイリストを作成"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists:
            self.playlists[user_id] = {}

        if name in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed("「{}」というプレイリストは既に存在します".format(name)),
                ephemeral=True
            )
            return

        self.playlists[user_id][name] = []
        self.save_playlists()

        await interaction.response.send_message(
            embed=create_success_embed("プレイリスト作成", f"「{name}」を作成しました")
        )

    @playlist_group.command(name='add', description='プレイリストに曲または YouTube プレイリストを追加')
    @app_commands.describe(
        name='プレイリスト名',
        url='YouTube URL（動画またはプレイリスト）',
        is_playlist='URL がYouTubeプレイリストの場合は True'
    )
    async def playlist_add(self, interaction: discord.Interaction, name: str, url: str, is_playlist: bool = False):
        """プレイリストに曲を追加（または YouTube プレイリストをインポート）"""
        # URL バリデーション
        if not ('youtube.com' in url or 'youtu.be' in url):
            await interaction.response.send_message(
                embed=create_error_embed("YouTube URL を入力してください"),
                ephemeral=True
            )
            return

        user_id = str(interaction.user.id)

        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            loop = asyncio.get_event_loop()

            if is_playlist:
                # YouTube プレイリスト全体を取得（制限なし）
                # 最初に動画IDのリストを素早く取得
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': 'in_playlist',
                    'lazy_playlist': True,  # すべてのページを取得
                    'skip_unavailable': True,  # 利用できない動画をスキップ
                    'ignoreerrors': True,  # エラーを無視
                    'socket_timeout': 30,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
                    },
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

                    if data is None or 'entries' not in data or not data['entries']:
                        await interaction.followup.send(
                            embed=create_error_embed("プレイリストが空です", "動画が含まれていません")
                        )
                        return

                    added_count = 0
                    failed_count = 0
                    unavailable_count = 0

                    logger.info(f"Playlist extraction started with {len(data['entries'])} entries")

                    for idx, entry in enumerate(data['entries'], 1):
                        try:
                            if entry is None:
                                unavailable_count += 1
                                continue

                            video_id = entry.get('id')
                            if not video_id:
                                unavailable_count += 1
                                continue

                            video_url = f"https://www.youtube.com/watch?v={video_id}"

                            try:
                                # 動画情報を取得
                                ydl_single = yt_dlp.YoutubeDL({
                                    'quiet': True,
                                    'no_warnings': True,
                                    'ignoreerrors': True,
                                    'skip_unavailable': True,  # 利用不可な動画をスキップ
                                    'socket_timeout': 30,
                                    'no_color': True,  # カラー出力を無効化
                                    'logger': logger,  # 標準エラーをログに出力
                                    'http_headers': {
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                    },
                                })
                                video_data = await loop.run_in_executor(None, lambda: ydl_single.extract_info(video_url, download=False))

                                if video_data is None:
                                    logger.debug(f"Video unavailable: {video_id}")
                                    unavailable_count += 1
                                    continue

                                # 必要なフィールドをチェック
                                if not video_data.get('url') or not video_data.get('webpage_url'):
                                    logger.debug(f"Video missing required fields: {video_id}")
                                    unavailable_count += 1
                                    continue

                                song = {
                                    'title': video_data.get('title', 'Unknown'),
                                    'url': video_data.get('url'),
                                    'webpage_url': video_data.get('webpage_url'),
                                    'duration': video_data.get('duration', 0)
                                }

                                self.playlists[user_id][name].append(song)
                                added_count += 1

                                if idx % 50 == 0:
                                    logger.info(f"Progress: {idx}/{len(data['entries'])} songs processed")
                            except Exception as e:
                                logger.debug(f"Failed to fetch video {video_id}: {str(e)}")
                                unavailable_count += 1
                                continue

                        except Exception as e:
                            logger.warning(f"Error processing entry: {str(e)}")
                            failed_count += 1
                            continue

                except Exception as e:
                    logger.error(f"Error extracting playlist info: {str(e)}")
                    await interaction.followup.send(
                        embed=create_error_embed(
                            "プレイリスト取得エラー",
                            f"プレイリスト情報の取得に失敗しました: {str(e)}"
                        )
                    )
                    return

                self.save_playlists()

                status = f"{added_count} 曲追加"
                if unavailable_count > 0:
                    status += f"（{unavailable_count} 曲利用不可）"
                if failed_count > 0:
                    status += f"（{failed_count} 曲エラー）"

                if added_count == 0:
                    await interaction.followup.send(
                        embed=create_error_embed(
                            "プレイリストインポート失敗",
                            f"追加できた曲がありません。利用不可: {unavailable_count}, エラー: {failed_count}"
                        )
                    )
                else:
                    await interaction.followup.send(
                        embed=create_success_embed(
                            "プレイリストインポート",
                            f"YouTube プレイリストから {status} しました"
                        )
                    )
            else:
                # 単一の動画を追加
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

                if 'entries' in data:
                    data = data['entries'][0]

                song = {
                    'title': data.get('title', 'Unknown'),
                    'url': data.get('url'),
                    'webpage_url': data.get('webpage_url'),
                    'duration': data.get('duration', 0)
                }

                self.playlists[user_id][name].append(song)
                self.save_playlists()

                await interaction.followup.send(
                    embed=create_success_embed("曲を追加", f"「{song['title']}」をプレイリスト「{name}」に追加しました")
                )
        except Exception as e:
            logger.error(f"Error adding song to playlist: {str(e)}")
            await interaction.followup.send(
                embed=create_error_embed("曲の追加に失敗しました", str(e))
            )

    @playlist_group.command(name='play', description='プレイリストを再生（キューに追加）')
    @app_commands.describe(name='プレイリスト名')
    async def playlist_play(self, interaction: discord.Interaction, name: str):
        """プレイリストの曲をキューに追加して再生"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                ephemeral=True
            )
            return

        playlist = self.playlists[user_id][name]

        if not playlist:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」は空のプレイリストです"),
                ephemeral=True
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                embed=create_error_embed("このコマンドはギルド内でのみ使用可能です"),
                ephemeral=True
            )
            return

        # ボイスチャネル確認
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except Exception as e:
            logger.warning(f"Failed to fetch member: {e}")
            member = None

        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                embed=create_error_embed("ボイスチャネルに接続してください"),
                ephemeral=True
            )
            return

        voice_channel = member.voice.channel
        voice_client = interaction.guild.voice_client

        # ボイスチャネルに接続
        if not voice_client:
            voice_client = await voice_channel.connect()
            # ボットをデフォン状態に設定（常にスピーカーミュート）
            try:
                await interaction.guild.me.edit(deafen=True)
            except discord.Forbidden:
                logger.warning("Failed to deafen bot: Missing 'Manage Members' permission")
            except Exception as e:
                logger.warning(f"Failed to deafen bot: {str(e)}")

        await interaction.response.defer()

        # キューの状態を確認
        queue = self.get_queue(interaction.guild.id)

        # キューが空の場合は直接再生（/play コマンドと同じ動作）
        if queue.current is None and not voice_client.is_playing():
            # プレイリストの再生処理を実行
            try:
                # シャッフル選択ビューを表示して再生
                view = PlaylistShuffleView(self, interaction, playlist, name, playlist[0], voice_client)
                embed = discord.Embed(
                    title="🎵 プレイリスト再生",
                    description=f"「{name}」を再生します",
                    color=discord.Color.blue()
                )
                embed.add_field(name="曲数", value=f"{len(playlist)} 曲", inline=False)
                embed.add_field(name="再生方法を選択してください", value="シャッフルまたは通常再生", inline=False)
                await interaction.followup.send(embed=embed, view=view)
            except Exception as e:
                logger.error(f"Error in playlist play: {str(e)}")
                await interaction.followup.send(
                    embed=create_error_embed("再生エラー", f"プレイリストの再生に失敗しました: {str(e)}")
                )
        else:
            # キューに曲が入っている、または既に再生中の場合は無条件に追加
            for song in playlist:
                queue.add(song)

            await interaction.followup.send(
                embed=create_success_embed(
                    "🎵 プレイリスト追加",
                    f"「{name}」の {len(playlist)} 曲をキューに追加しました"
                )
            )

    @playlist_group.command(name='delete', description='プレイリストを削除')
    @app_commands.describe(name='プレイリスト名')
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        """プレイリストを削除"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                ephemeral=True
            )
            return

        del self.playlists[user_id][name]
        self.save_playlists()

        await interaction.response.send_message(
            embed=create_success_embed("プレイリスト削除", f"「{name}」を削除しました")
        )

    @playlist_group.command(name='remove', description='プレイリストから曲を削除')
    @app_commands.describe(
        name='プレイリスト名',
        index='削除する曲のインデックス（1から始まる）'
    )
    async def playlist_remove(self, interaction: discord.Interaction, name: str, index: int):
        """プレイリストから指定した曲を削除"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                ephemeral=True
            )
            return

        playlist = self.playlists[user_id][name]

        if index < 1 or index > len(playlist):
            await interaction.response.send_message(
                embed=create_error_embed(
                    "無効なインデックス",
                    f"プレイリストには {len(playlist)} 曲あります"
                ),
                ephemeral=True
            )
            return

        removed_song = playlist.pop(index - 1)
        self.save_playlists()

        await interaction.response.send_message(
            embed=create_success_embed(
                "曲を削除",
                f"「{removed_song['title']}」をプレイリスト「{name}」から削除しました"
            )
        )

    @playlist_group.command(name='share', description='プレイリストをコード化して共有')
    @app_commands.describe(name='プレイリスト名')
    async def playlist_share(self, interaction: discord.Interaction, name: str):
        """プレイリストを共有可能なコード化形式で出力"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                ephemeral=True
            )
            return

        playlist = self.playlists[user_id][name]

        if not playlist:
            await interaction.response.send_message(
                embed=create_error_embed(f"「{name}」は空のプレイリストです"),
                ephemeral=True
            )
            return

        # プレイリストデータをシリアライズ
        playlist_data = {
            'name': name,
            'created_by': str(interaction.user),
            'songs': playlist
        }

        try:
            # JSON エンコード
            json_str = json.dumps(playlist_data, ensure_ascii=False)
            # Base64 エンコード
            encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

            # コードを分割（Discord メッセージ上限対応）
            code_chunks = [encoded[i:i+1900] for i in range(0, len(encoded), 1900)]

            embed = discord.Embed(
                title="📤 プレイリスト共有",
                color=discord.Color.green(),
                description=f"プレイリスト「{name}」を共有できます"
            )
            embed.add_field(name="曲数", value=f"{len(playlist)} 曲", inline=True)
            embed.add_field(name="作成者", value=str(interaction.user), inline=True)
            embed.add_field(
                name="使用方法",
                value="/playlist import <コード> でインポートできます",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

            # コードを送信
            for i, chunk in enumerate(code_chunks):
                chunk_embed = discord.Embed(
                    title=f"共有コード ({i+1}/{len(code_chunks)})",
                    color=discord.Color.blue(),
                    description=f"```\n{chunk}\n```"
                )
                await interaction.followup.send(embed=chunk_embed)

            logger.info(f"User {interaction.user.name} shared playlist: {name}")

        except Exception as e:
            logger.error(f"Error sharing playlist: {str(e)}")
            await interaction.followup.send(
                embed=create_error_embed("共有失敗", str(e))
            )

    @playlist_group.command(name='import', description='共有されたプレイリストをインポート')
    @app_commands.describe(code='共有コード')
    async def playlist_import(self, interaction: discord.Interaction, code: str):
        """共有されたプレイリストをインポート"""
        user_id = str(interaction.user.id)

        try:
            # Base64 デコード
            decoded = base64.b64decode(code).decode('utf-8')
            playlist_data = json.loads(decoded)

            # データ検証
            if not isinstance(playlist_data, dict) or 'name' not in playlist_data or 'songs' not in playlist_data:
                await interaction.response.send_message(
                    embed=create_error_embed("無効なプレイリストコード", "コードが破損しているか、形式が正しくありません"),
                    ephemeral=True
                )
                return

            playlist_name = playlist_data['name']
            songs = playlist_data['songs']

            if not songs:
                await interaction.response.send_message(
                    embed=create_error_embed("空のプレイリスト", "このプレイリストには曲が含まれていません"),
                    ephemeral=True
                )
                return

            # ユーザーの プレイリストを初期化
            if user_id not in self.playlists:
                self.playlists[user_id] = {}

            # 同じ名前のプレイリストが存在する場合の処理
            if playlist_name in self.playlists[user_id]:
                # 名前を変更
                counter = 1
                original_name = playlist_name
                while f"{original_name}_{counter}" in self.playlists[user_id]:
                    counter += 1
                playlist_name = f"{original_name}_{counter}"

            # プレイリストをインポート
            imported_songs = []
            for song in songs:
                if isinstance(song, dict) and 'title' in song and 'url' in song:
                    imported_songs.append({
                        'title': song['title'],
                        'url': song['url'],
                        'webpage_url': song.get('url'),
                        'duration': song.get('duration', 0)
                    })

            if not imported_songs:
                await interaction.response.send_message(
                    embed=create_error_embed("インポート失敗", "有効な曲情報が見つかりませんでした"),
                    ephemeral=True
                )
                return

            self.playlists[user_id][playlist_name] = imported_songs
            self.save_playlists()

            # 作成者情報を表示
            created_by = playlist_data.get('created_by', '不明')

            embed = discord.Embed(
                title="📥 プレイリストインポート",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="プレイリスト名", value=f"**{playlist_name}**", inline=False)
            embed.add_field(name="曲数", value=f"**{len(imported_songs)}** 曲", inline=True)
            embed.add_field(name="作成者", value=f"**{created_by}**", inline=True)
            embed.set_footer(text="このプレイリストは /playlist load で再生できます")

            await interaction.response.send_message(embed=embed)
            logger.info(f"User {interaction.user.name} imported playlist: {playlist_name} ({len(imported_songs)} songs)")

        except (base64.binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            await interaction.response.send_message(
                embed=create_error_embed("デコード失敗", "コードが正しく形式化されていません"),
                ephemeral=True
            )
            logger.error(f"Failed to decode playlist code: {str(code[:20])}")
        except Exception as e:
            logger.error(f"Error importing playlist: {str(e)}")
            await interaction.response.send_message(
                embed=create_error_embed("インポート失敗", str(e)),
                ephemeral=True
            )

    @playlist_group.command(name='list', description='プレイリスト一覧を表示')
    @app_commands.describe(name='プレイリスト名（指定時は詳細表示）')
    async def playlist_list(self, interaction: discord.Interaction, name: str = None):
        """プレイリスト一覧を表示（詳細表示も可能）"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or not self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed("プレイリストがありません"),
                ephemeral=True
            )
            return

        playlists = self.playlists[user_id]

        if name:
            # 詳細表示
            if name not in playlists:
                await interaction.response.send_message(
                    embed=create_error_embed(f"「{name}」というプレイリストが見つかりません"),
                    ephemeral=True
                )
                return

            songs = playlists[name]
            embed = discord.Embed(
                title=f"📋 プレイリスト「{name}」",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="曲数", value=f"{len(songs)} 曲", inline=True)

            if songs:
                songs_list = "\n".join(
                    [f"{i+1}. {song['title'][:50]}" for i, song in enumerate(songs[:20])]
                )
                if len(songs) > 20:
                    songs_list += f"\n... ほか {len(songs) - 20} 曲"

                embed.add_field(
                    name="曲一覧",
                    value=songs_list,
                    inline=False
                )

            embed.set_footer(text="/playlist remove で曲を削除できます")
            await interaction.response.send_message(embed=embed)
        else:
            # 一覧表示
            embed = discord.Embed(
                title="📋 プレイリスト一覧",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            total_songs = 0
            for plist_name, songs in playlists.items():
                embed.add_field(
                    name=plist_name,
                    value=f"{len(songs)} 曲",
                    inline=False
                )
                total_songs += len(songs)

            embed.set_footer(text=f"全{len(playlists)}個のプレイリスト、全{total_songs}曲 | /playlist list <プレイリスト名> で詳細表示")

            await interaction.response.send_message(embed=embed)


class PlaylistShuffleView(discord.ui.View):
    """プレイリスト再生時のシャッフル選択ビュー"""

    def __init__(self, music_cog, interaction, playlist, playlist_name, first_song, voice_client):
        super().__init__(timeout=None)  # タイムアウトなし
        self.music_cog = music_cog
        self.interaction = interaction
        self.playlist = playlist
        self.playlist_name = playlist_name
        self.first_song = first_song
        self.voice_client = voice_client
        self.shuffle = False

    @discord.ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """シャッフル再生"""
        self.shuffle = True
        await interaction.response.defer()
        await self._play_playlist()

    @discord.ui.button(label="📋 通常再生", style=discord.ButtonStyle.secondary)
    async def normal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """通常再生"""
        self.shuffle = False
        await interaction.response.defer()
        await self._play_playlist()

    async def _play_playlist(self):
        """プレイリストを再生"""
        try:
            user_id = str(self.interaction.user.id)
            queue = self.music_cog.get_queue(self.interaction.guild.id)

            # プレイリストをコピーして準備
            songs_to_play = list(self.playlist)

            if self.shuffle:
                # 最初の曲以外をシャッフル
                remaining_songs = songs_to_play[1:]
                import random
                random.shuffle(remaining_songs)
                songs_to_play = [songs_to_play[0]] + remaining_songs

            first_song = songs_to_play[0]

            # デバッグログ
            logger.info(f"Playing playlist: {self.playlist_name}")
            logger.info(f"First song: {first_song}")
            logger.info(f"Shuffle: {self.shuffle}, Songs count: {len(songs_to_play)}")

            # チャネル ID を保存（通知用）
            if queue.notification_channel_id is None:
                queue.notification_channel_id = self.interaction.channel.id

            # キューに曲が入っていない場合のみ即座に再生
            if queue.current is None and not self.voice_client.is_playing():
                player = await YTDLSource.from_url(first_song['webpage_url'], loop=self.music_cog.bot.loop, stream=True)
                self.voice_client.play(player, after=lambda e: self.music_cog.play_next(self.interaction.guild))
                queue.current = first_song
                queue.start_time = time.time()

                # 再生履歴に記録
                try:
                    self.music_cog.db.record_music_history(
                        user_id=user_id,
                        title=first_song['title'],
                        url=first_song['webpage_url'],
                        genre=None,
                        duration=first_song.get('duration')
                    )
                except Exception as e:
                    logger.warning(f"Failed to record music history: {str(e)}")

                # 残りの曲をキューに追加
                for song in songs_to_play[1:]:
                    queue.add(song)

                embed = discord.Embed(
                    title="🎵 再生中",
                    description=f"[{first_song['title']}]({first_song['webpage_url']})",
                    color=discord.Color.blue()
                )
                if first_song.get('thumbnail'):
                    embed.set_thumbnail(url=first_song['thumbnail'])
                embed.add_field(name="プレイリスト", value=self.playlist_name, inline=False)
                embed.add_field(name="曲数", value=f"{len(songs_to_play)} 曲", inline=False)
                if self.shuffle:
                    embed.add_field(name="モード", value="🔀 シャッフル", inline=False)
                if first_song.get('duration'):
                    embed.add_field(name="再生時間", value=self.music_cog.format_duration(first_song['duration']), inline=False)

                await self.interaction.followup.send(embed=embed)
            else:
                # キューに曲が入っている、または既に再生中の場合
                for song in songs_to_play:
                    queue.add(song)

                await self.interaction.followup.send(
                    embed=create_success_embed(
                        "🎵 プレイリスト追加",
                        f"「{self.playlist_name}」の {len(songs_to_play)} 曲をキューに追加しました"
                    )
                )

        except Exception as e:
            logger.error(f"Error playing playlist: {str(e)}")
            await self.interaction.followup.send(
                embed=create_error_embed(
                    "再生エラー",
                    f"プレイリストの再生に失敗しました: {str(e)}"
                )
            )


class MusicControlView(discord.ui.View):
    """音楽コントロール用のボタンビュー"""

    def __init__(self, music_cog, guild_id):
        super().__init__(timeout=None)  # タイムアウトなし
        self.music_cog = music_cog
        self.guild_id = guild_id

    @discord.ui.button(label="⏸ 一時停止", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """一時停止ボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸ 一時停止しました", ephemeral=True)
        else:
            await interaction.response.send_message("再生中の音楽がありません", ephemeral=True)

    @discord.ui.button(label="▶ 再開", style=discord.ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """再開ボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶ 再開しました", ephemeral=True)
        else:
            await interaction.response.send_message("一時停止中の音楽がありません", ephemeral=True)

    @discord.ui.button(label="⏭ スキップ", style=discord.ButtonStyle.danger)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """スキップボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭ スキップしました", ephemeral=True)
        else:
            await interaction.response.send_message("再生中の音楽がありません", ephemeral=True)

    @discord.ui.button(label="🔁 ループ", style=discord.ButtonStyle.secondary)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """ループ切り替えボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        queue = self.music_cog.get_queue(interaction.guild.id)

        if queue.repeat_mode == RepeatMode.OFF:
            queue.repeat_mode = RepeatMode.ONE
            mode_text = "🎵 1曲リピート"
        elif queue.repeat_mode == RepeatMode.ONE:
            queue.repeat_mode = RepeatMode.ALL
            mode_text = "🔁 全曲リピート"
        else:
            queue.repeat_mode = RepeatMode.OFF
            mode_text = "ループOFF"

        await interaction.response.send_message(f"{mode_text}", ephemeral=True)

    @discord.ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.secondary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """シャッフル切り替えボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        queue = self.music_cog.get_queue(interaction.guild.id)
        queue.shuffle = not queue.shuffle

        status = "ON" if queue.shuffle else "OFF"
        await interaction.response.send_message(f"🔀 シャッフル: {status}", ephemeral=True)

    @discord.ui.button(label="🔊 +5%", style=discord.ButtonStyle.green)
    async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """ボリューム+ボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_playing():
            current_volume = voice_client.source.volume
            new_volume = min(1.0, current_volume + 0.05)
            voice_client.source.volume = new_volume
            percentage = int(new_volume * 100)
            await interaction.response.send_message(f"🔊 音量: {percentage}%", ephemeral=True)
        else:
            await interaction.response.send_message("再生中の音楽がありません", ephemeral=True)

    @discord.ui.button(label="🔉 -5%", style=discord.ButtonStyle.green)
    async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """ボリューム-ボタン"""
        if interaction.guild.id != self.guild_id:
            await interaction.response.defer()
            return

        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_playing():
            current_volume = voice_client.source.volume
            new_volume = max(0.0, current_volume - 0.05)
            voice_client.source.volume = new_volume
            percentage = int(new_volume * 100)
            await interaction.response.send_message(f"🔉 音量: {percentage}%", ephemeral=True)
        else:
            await interaction.response.send_message("再生中の音楽がありません", ephemeral=True)


class QueueView(discord.ui.View):
    """キュー表示用のボタンビュー（ページネーション対応）"""

    def __init__(self, music_cog, queue, total_duration, total_songs, requester):
        super().__init__(timeout=300)
        self.music_cog = music_cog
        self.queue = queue
        self.total_duration = total_duration
        self.total_songs = total_songs
        self.requester = requester
        self.page = 0
        self.songs_per_page = 10
        self.update_buttons()

    def get_embed(self) -> discord.Embed:
        """現在のページの embed を生成"""
        embed = discord.Embed(
            title="📜 キュー情報",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # 現在再生中の曲
        if self.queue.current:
            position = self.queue.get_position()
            duration = self.queue.current.get('duration', 0)
            duration_text = self.music_cog.format_duration(duration) if duration else "不明"
            position_text = self.music_cog.format_duration(position)

            # 進捗バーを作成（20文字の長さ）
            if duration > 0:
                progress = int((position / duration) * 20)
                progress_bar = "█" * progress + "░" * (20 - progress)
            else:
                progress_bar = "░" * 20

            current_info = f"**{self.queue.current['title']}**\n"
            current_info += f"`{progress_bar}` {position_text} / {duration_text}\n"
            current_info += f"リクエスト: {self.queue.current.get('requester', '不明')}"

            embed.add_field(
                name="🎵 再生中",
                value=current_info,
                inline=False
            )

        # キュー内の次の曲（ページネーション）
        if not self.queue.is_empty():
            queue_count = len(self.queue.queue)
            start_idx = self.page * self.songs_per_page
            end_idx = start_idx + self.songs_per_page
            current_songs = self.queue.queue[start_idx:end_idx]

            queue_text = f"**ページ {self.page + 1}/{(queue_count + self.songs_per_page - 1) // self.songs_per_page}**\n\n"

            for i, song in enumerate(current_songs):
                duration = self.music_cog.format_duration(song['duration']) if song.get('duration') else "不明"
                title = song['title']
                # タイトルが長い場合は短縮
                if len(title) > 50:
                    title = title[:47] + "..."
                queue_text += f"`{start_idx + i + 1:2d}.` {title}\n"
                queue_text += f"      ⏱️ {duration}\n"

            embed.add_field(
                name=f"⏭️ キュー ({queue_count} 曲)",
                value=queue_text or "キューが空です",
                inline=False
            )

        # ステータスと統計
        status = []
        if self.queue.repeat_mode == RepeatMode.ONE:
            status.append("🔁 1曲リピート")
        elif self.queue.repeat_mode == RepeatMode.ALL:
            status.append("🔁 全曲リピート")
        if self.queue.shuffle:
            status.append("🔀 シャッフル")

        status_text = " | ".join(status) if status else "通常モード"

        total_duration_text = self.music_cog.format_duration(self.total_duration)
        stats_text = f"**曲数:** {self.total_songs}\n"
        stats_text += f"**総再生時間:** {total_duration_text}"

        embed.add_field(name="📊 統計", value=stats_text, inline=True)
        embed.add_field(name="⚙️ ステータス", value=status_text, inline=True)

        embed.set_footer(text=f"ボイスチャネル接続状態: {'接続中' if self.queue else '未接続'}")

        return embed

    def update_buttons(self):
        """現在のページに応じてボタンを更新"""
        self.clear_items()

        queue_count = len(self.queue.queue)

        # ナビゲーションボタン
        if self.page > 0:
            prev_button = discord.ui.Button(label="← 前へ", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)

        # ページ情報
        total_pages = (queue_count + self.songs_per_page - 1) // self.songs_per_page if queue_count > 0 else 1
        page_button = discord.ui.Button(
            label=f"ページ {self.page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_button)

        if (self.page + 1) * self.songs_per_page < queue_count:
            next_button = discord.ui.Button(label="次へ →", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)

    async def prev_page(self, interaction: discord.Interaction):
        """前のページへ"""
        if interaction.user != self.requester:
            await interaction.response.send_message(
                embed=create_error_embed("このボタンは使用できません"),
                ephemeral=True
            )
            return

        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        """次のページへ"""
        if interaction.user != self.requester:
            await interaction.response.send_message(
                embed=create_error_embed("このボタンは使用できません"),
                ephemeral=True
            )
            return

        queue_count = len(self.queue.queue)
        if (self.page + 1) * self.songs_per_page < queue_count:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


class SearchView(discord.ui.View):
    """検索結果用のボタンビュー（ページネーション対応）"""

    def __init__(self, music_cog, songs, requester, query: str = ""):
        super().__init__(timeout=60)
        self.music_cog = music_cog
        self.all_songs = songs
        self.requester = requester
        self.query = query
        self.page = 0
        self.songs_per_page = 5
        self.update_buttons()

    def get_embed(self) -> discord.Embed:
        """現在のページの embed を生成"""
        embed = discord.Embed(
            title="🔍 検索結果",
            description=f"「{self.query}」の検索結果（全 {len(self.all_songs)} 件）",
            color=discord.Color.blue()
        )

        start_idx = self.page * self.songs_per_page
        end_idx = start_idx + self.songs_per_page
        current_songs = self.all_songs[start_idx:end_idx]

        description = f"**ページ {self.page + 1}/{(len(self.all_songs) + self.songs_per_page - 1) // self.songs_per_page}**\n\n"
        for i, song in enumerate(current_songs):
            title = song.get('title', 'Unknown')
            duration = self.music_cog.format_duration(song.get('duration', 0))
            description += f"{start_idx + i + 1}. {title} ({duration})\n"

        embed.description += "\n" + description
        if len(self.all_songs) > self.songs_per_page:
            embed.set_footer(text="下のボタンをクリックして再生する曲を選択するか、「次へ」で更に検索結果を見てください")
        else:
            embed.set_footer(text="下のボタンをクリックして再生する曲を選択してください")

        return embed

    def update_buttons(self):
        """現在のページに応じてボタンを更新"""
        self.clear_items()

        # 現在のページの曲リストを取得
        start_idx = self.page * self.songs_per_page
        end_idx = start_idx + self.songs_per_page
        current_songs = self.all_songs[start_idx:end_idx]

        # 曲選択ボタン
        for i, song in enumerate(current_songs):
            button = discord.ui.Button(
                label=f"{self.page * self.songs_per_page + i + 1}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.create_callback(start_idx + i)
            self.add_item(button)

        # ナビゲーションボタン
        if self.page > 0:
            prev_button = discord.ui.Button(label="← 前へ", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)

        if end_idx < len(self.all_songs):
            next_button = discord.ui.Button(label="次へ →", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)

    async def prev_page(self, interaction: discord.Interaction):
        """前のページへ"""
        if interaction.user != self.requester:
            await interaction.response.send_message(
                embed=create_error_embed("このボタンは使用できません"),
                ephemeral=True
            )
            return

        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        """次のページへ"""
        if interaction.user != self.requester:
            await interaction.response.send_message(
                embed=create_error_embed("このボタンは使用できません"),
                ephemeral=True
            )
            return

        if (self.page + 1) * self.songs_per_page < len(self.all_songs):
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            logger.info(f"Search callback triggered: index={index}, user={interaction.user.name}")

            if interaction.user != self.requester:
                logger.warning(f"Search callback: User {interaction.user.name} is not the requester")
                await interaction.response.send_message(
                    embed=create_error_embed("このボタンは使用できません"),
                    ephemeral=True
                )
                return

            # Check voice channel before proceeding
            logger.info(f"Fetching member for user {interaction.user.id}")
            member = await interaction.guild.fetch_member(interaction.user.id)
            if not member or not member.voice or not member.voice.channel:
                logger.warning(f"Search callback: User not in voice channel")
                await interaction.response.send_message(
                    embed=create_error_embed("ボイスチャネルに接続してください"),
                    ephemeral=True
                )
                return

            logger.info(f"User is in voice channel: {member.voice.channel.name}")
            logger.info(f"Deferring interaction...")
            await interaction.response.defer()
            logger.info(f"Interaction deferred successfully")

            try:
                logger.info(f"Getting song at index {index}")
                song = self.all_songs[index]
                logger.info(f"Song selected: {song['title']}")

                voice_channel = member.voice.channel
                voice_client = interaction.guild.voice_client
                logger.info(f"Voice client status: {voice_client}")

                # ボイスチャネルに接続
                if not voice_client:
                    logger.info(f"Connecting to voice channel: {voice_channel.name}")
                    voice_client = await voice_channel.connect()
                    logger.info(f"Connected to voice channel")
                    try:
                        await interaction.guild.me.edit(deafen=True)
                        logger.info(f"Bot deafened")
                    except Exception as e:
                        logger.warning(f"Failed to deafen bot: {str(e)}")

                # キューを取得
                logger.info(f"Getting queue for guild {interaction.guild.id}")
                queue = self.music_cog.get_queue(interaction.guild.id)
                logger.info(f"Queue status: current={queue.current is not None}, is_playing={voice_client.is_playing()}")

                # キューに曲が入っていない場合のみ即座に再生
                if queue.current is None and not voice_client.is_playing():
                    logger.info(f"Starting playback of {song['title']}")
                    try:
                        logger.info(f"Creating YTDLSource from: {song['webpage_url']}")
                        player = await YTDLSource.from_url(song['webpage_url'], loop=self.music_cog.bot.loop, stream=True)
                        logger.info(f"YTDLSource created successfully")

                        logger.info(f"Playing audio")
                        voice_client.play(player, after=lambda e: self.music_cog.play_next(interaction.guild))
                        queue.current = song
                        queue.start_time = time.time()
                        logger.info(f"Playback started")

                        # 再生履歴に記録
                        try:
                            logger.info(f"Recording music history")
                            self.music_cog.db.record_music_history(
                                user_id=str(interaction.user.id),
                                title=song['title'],
                                url=song['webpage_url'],
                                genre=None,
                                duration=song.get('duration')
                            )
                            logger.info(f"Music history recorded")
                        except Exception as e:
                            logger.warning(f"Failed to record music history: {str(e)}")

                        logger.info(f"Creating embed message")
                        embed = discord.Embed(
                            title="🎵 再生中",
                            description=f"[{song['title']}]({song['webpage_url']})",
                            color=discord.Color.blue()
                        )
                        if song.get('thumbnail'):
                            embed.set_thumbnail(url=song['thumbnail'])
                        embed.add_field(name="リクエスト", value=interaction.user.mention, inline=False)
                        if song.get('duration'):
                            embed.add_field(name="再生時間", value=self.music_cog.format_duration(song['duration']), inline=False)

                        logger.info(f"Sending followup message")
                        await interaction.followup.send(embed=embed, view=MusicControlView(self.music_cog, interaction.guild.id))
                        logger.info(f"Followup message sent successfully")
                    except Exception as e:
                        logger.error(f"Error during playback: {str(e)}", exc_info=True)
                        raise
                else:
                    logger.info(f"Queue not empty, adding to queue")
                    # キューに追加
                    queue.add(song)
                    logger.info(f"Song added to queue at position {len(queue.queue)}")

                    embed = discord.Embed(
                        title="➕ キューに追加",
                        description=f"[{song['title']}]({song['webpage_url']})",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="キューの位置", value=f"#{len(queue.queue)}", inline=False)

                    await interaction.followup.send(embed=embed)
                    logger.info(f"Queue addition message sent")

            except Exception as e:
                logger.error(f"Error in search callback: {str(e)}", exc_info=True)
                try:
                    await interaction.followup.send(
                        embed=create_error_embed("曲の再生に失敗しました", str(e)),
                        ephemeral=True
                    )
                except Exception as e2:
                    logger.error(f"Error sending error message: {str(e2)}")

        return callback

    def cog_unload(self):
        """Cog がアンロードされる時の処理"""
        self.auto_disconnect_task.cancel()
        logger.info("Music Cog unloaded")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
    logger.info("Music Cog loaded")
