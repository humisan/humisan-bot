import discord
from discord.ext import commands
from discord import app_commands
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger
import yt_dlp
import asyncio
from typing import Dict, List
import json
import os
import random
from enum import Enum
import time

logger = setup_logger(__name__)

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
    'http_headers': {  # ヘッダーを追加
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    },
    'extract_flat': 'in_playlist',  # プレイリストの動画IDを高速に取得
}

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
        self.queues: Dict[int, MusicQueue] = {}
        self.favorites_file = 'favorites.json'
        self.favorites = self.load_favorites()
        self.playlists_file = 'playlists.json'
        self.playlists = self.load_playlists()
        self.skip_votes: Dict[int, set] = {}  # guild_id -> {user_ids}

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
            return data.get('entries', [])
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
            is_playlist_limited = False

            if 'entries' in data:
                # プレイリストの場合（最大25曲まで）
                max_songs = 25
                total_entries = len(data.get('entries', []))

                for i, entry in enumerate(data['entries']):
                    # 25曲に達したら終了
                    if len(songs_to_add) >= max_songs:
                        is_playlist_limited = True
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

                # プレイリストが25曲以上の場合は警告を表示
                if total_entries > max_songs:
                    logger.info(f"Playlist has {total_entries} songs, limited to {max_songs} songs")
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

                if is_playlist_limited:
                    embed.add_field(name="⚠️ 注意", value="プレイリストが25曲以上あるため、最初の25曲のみキューに追加しました", inline=False)

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

                if is_playlist_limited:
                    embed.add_field(name="⚠️ 注意", value="プレイリストが25曲以上あるため、最初の25曲のみキューに追加しました", inline=False)

                await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error playing music: {str(e)}")
            await interaction.followup.send(
                embed=create_error_embed("音楽の再生に失敗しました", str(e))
            )

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

    @app_commands.command(name='skip', description='現在の曲をスキップします')
    async def skip(self, interaction: discord.Interaction):
        """曲をスキップ"""
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message(
                embed=create_error_embed("現在再生中の音楽がありません"),
                ephemeral=True
            )
            return

        voice_client.stop()
        await interaction.response.send_message(embed=create_success_embed("⏭️ スキップ", "曲をスキップしました"))

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

        embed = discord.Embed(
            title="📜 音楽キュー",
            color=discord.Color.blue()
        )

        if queue.current:
            position = queue.get_position()
            duration_text = self.format_duration(queue.current['duration']) if queue.current['duration'] else "不明"
            position_text = self.format_duration(position)
            embed.add_field(
                name="🎵 再生中",
                value=f"{queue.current['title']}\n{position_text} / {duration_text}",
                inline=False
            )

        if not queue.is_empty():
            queue_text = ""
            for i, song in enumerate(queue.queue[:10], 1):
                duration = self.format_duration(song['duration']) if song['duration'] else "不明"
                queue_text += f"{i}. {song['title']} ({duration})\n"

            if len(queue.queue) > 10:
                queue_text += f"\n... 他 {len(queue.queue) - 10} 曲"

            embed.add_field(name="次の曲", value=queue_text, inline=False)

        # ステータス
        status = []
        if queue.repeat_mode == RepeatMode.ONE:
            status.append("🔁 1曲リピート")
        elif queue.repeat_mode == RepeatMode.ALL:
            status.append("🔁 全曲リピート")
        if queue.shuffle:
            status.append("🔀 シャッフル")

        if status:
            embed.add_field(name="ステータス", value=" | ".join(status), inline=False)

        await interaction.response.send_message(embed=embed)

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

        if not queue.is_empty() or queue.repeat_mode == RepeatMode.ALL:
            song = queue.next()
            if song:
                loop = asyncio.get_event_loop()

                try:
                    player = await YTDLSource.from_url(song['webpage_url'], loop=loop, stream=True)
                    voice_client.play(player, after=lambda e: self.play_next(guild))

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

    @playlist_group.command(name='add', description='プレイリストに曲を追加')
    @app_commands.describe(
        name='プレイリスト名',
        url='YouTube URL'
    )
    async def playlist_add(self, interaction: discord.Interaction, name: str, url: str):
        """プレイリストに曲を追加"""
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
            # 曲情報を取得
            loop = asyncio.get_event_loop()
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

    @playlist_group.command(name='load', description='プレイリストをキューに追加')
    @app_commands.describe(name='プレイリスト名')
    async def playlist_load(self, interaction: discord.Interaction, name: str):
        """プレイリストの曲をキューに追加"""
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

        queue = self.get_queue(interaction.guild.id)

        for song in playlist:
            queue.add(song)

        await interaction.response.send_message(
            embed=create_success_embed(
                "プレイリスト追加",
                f"「{name}」の {len(playlist)} 曲をキューに追加しました"
            )
        )

    @playlist_group.command(name='list', description='プレイリスト一覧を表示')
    async def playlist_list(self, interaction: discord.Interaction):
        """プレイリスト一覧を表示"""
        user_id = str(interaction.user.id)

        if user_id not in self.playlists or not self.playlists[user_id]:
            await interaction.response.send_message(
                embed=create_error_embed("プレイリストがありません"),
                ephemeral=True
            )
            return

        playlists = self.playlists[user_id]

        embed = discord.Embed(
            title="📋 プレイリスト一覧",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        for plist_name, songs in playlists.items():
            embed.add_field(
                name=plist_name,
                value=f"{len(songs)} 曲",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


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
            if interaction.user != self.requester:
                await interaction.response.send_message(
                    embed=create_error_embed("このボタンは使用できません"),
                    ephemeral=True
                )
                return

            song = self.all_songs[index]
            query = song['webpage_url']

            # interaction を defer して play コマンドを実行
            await interaction.response.defer()

            # play コマンドを実行
            await self.music_cog.play(interaction, query)

        return callback


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
