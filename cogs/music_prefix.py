"""
プレフィックスコマンド（h!p, h!search, h!np, h!pause, h!skip, h!vol）
"""

import discord
from discord.ext import commands
import asyncio
from utils.helpers import create_error_embed, create_success_embed
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MusicPrefix(commands.Cog):
    """音楽プレフィックスコマンド"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Music Cogへのアクセスを取得するための参照
        self.music_cog = None

    def _get_music_cog(self):
        """Music Cog を取得"""
        if not self.music_cog:
            self.music_cog = self.bot.get_cog('Music')
        return self.music_cog

    # ==================== h!p - 再生 ====================

    @commands.command(name='p', aliases=['play'])
    async def prefix_play(self, ctx: commands.Context, *, query: str = None):
        """
        曲を再生（URL or キーワード）

        使用例:
            h!p https://www.youtube.com/watch?v=...  # URL で直接再生
            h!p YOASOBI 夜遊び                        # キーワードで検索＆再生
        """
        if not query:
            await ctx.send(embed=create_error_embed(
                "使用例",
                "h!p [URL or 曲名]\n"
                "例: h!p YOASOBI 夜遊び"
            ))
            return

        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        # ボイスチャネル確認
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=create_error_embed("ボイスチャネルに接続してください"))
            return

        # URL か キーワードか判定
        if 'youtube.com' in query or 'youtu.be' in query:
            # URL の場合は直接再生
            await ctx.defer()
            await music_cog._perform_play(ctx, query)
        else:
            # キーワードの場合は検索結果を表示
            await ctx.defer()
            try:
                songs = await music_cog.search_songs(query, limit=20)

                if not songs:
                    await ctx.send(embed=create_error_embed("曲が見つかりません"))
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
                    duration = music_cog.format_duration(song.get('duration', 0))
                    description += f"{i}. {title} ({duration})\n"

                embed.description += "\n" + description
                if len(songs) > 5:
                    embed.set_footer(text="リアクションで曲を選択してください（1-5 の数字）")
                else:
                    embed.set_footer(text="リアクションで曲を選択してください（1-5 の数字）")

                # SearchView を使用（slash command と同じ処理）
                from cogs.music import SearchView
                view = SearchView(music_cog, songs, ctx.author, query)
                await ctx.send(embed=view.get_embed(), view=view)

            except Exception as e:
                logger.error(f"Search error: {str(e)}")
                await ctx.send(embed=create_error_embed("検索に失敗しました", str(e)))

    # ==================== h!search - 検索 ====================

    @commands.command(name='search')
    async def prefix_search(self, ctx: commands.Context, *, query: str = None):
        """
        曲を検索

        使用例:
            h!search YOASOBI 夜遊び
        """
        if not query:
            await ctx.send(embed=create_error_embed(
                "使用例",
                "h!search [曲名]\n"
                "例: h!search YOASOBI 夜遊び"
            ))
            return

        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        await ctx.defer()

        try:
            songs = await music_cog.search_songs(query, limit=20)

            if not songs:
                await ctx.send(embed=create_error_embed("曲が見つかりません"))
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
                duration = music_cog.format_duration(song.get('duration', 0))
                description += f"{i}. {title} ({duration})\n"

            embed.description += "\n" + description
            if len(songs) > 5:
                embed.set_footer(text="リアクションで曲を選択してください（1-5 の数字）")
            else:
                embed.set_footer(text="リアクションで曲を選択してください（1-5 の数字）")

            # SearchView を使用
            from cogs.music import SearchView
            view = SearchView(music_cog, songs, ctx.author, query)
            await ctx.send(embed=view.get_embed(), view=view)

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            await ctx.send(embed=create_error_embed("検索に失敗しました", str(e)))

    # ==================== h!np - 現在再生中 ====================

    @commands.command(name='np')
    async def prefix_np(self, ctx: commands.Context):
        """
        現在再生中の曲を表示

        使用例:
            h!np
        """
        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        queue = music_cog.get_queue(ctx.guild.id)

        if not queue.current:
            await ctx.send(embed=create_error_embed("再生中の曲がありません"))
            return

        # 再生情報を取得
        voice_client = ctx.guild.voice_client
        current_time = 0
        duration = queue.current.get('duration', 0)

        if voice_client and voice_client.source:
            # 現在の再生時間を計算（ローカル時間 - 開始時間）
            import time
            current_time = int(time.time() - queue.start_time) if queue.start_time else 0

        # 再生時間をフォーマット
        current_str = music_cog.format_duration(current_time)
        duration_str = music_cog.format_duration(duration)
        progress_str = f"{current_str} / {duration_str}"

        # プログレスバーを作成
        if duration > 0:
            progress = int((current_time / duration) * 20)
            progress_bar = "▰" * progress + "▱" * (20 - progress)
        else:
            progress_bar = "▰" * 20

        title = queue.current.get('title', 'Unknown')
        uploader = queue.current.get('uploader', 'Unknown')

        embed = discord.Embed(
            title="🎵 現在再生中",
            description=f"**{title}**\n{uploader}",
            color=discord.Color.green()
        )
        embed.add_field(name="再生時間", value=f"{progress_bar}\n{progress_str}", inline=False)

        if queue.is_paused:
            embed.add_field(name="ステータス", value="⏸ 一時停止中", inline=False)

        await ctx.send(embed=embed)

    # ==================== h!pause - 一時停止/再開 ====================

    @commands.command(name='pause')
    async def prefix_pause(self, ctx: commands.Context):
        """
        再生を一時停止/再開（トグル）

        使用例:
            h!pause
        """
        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        voice_client = ctx.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await ctx.send(embed=create_error_embed("再生中の曲がありません"))
            return

        queue = music_cog.get_queue(ctx.guild.id)

        if queue.is_paused:
            # 再開
            voice_client.resume()
            queue.is_paused = False
            await ctx.send(embed=create_success_embed("▶ 再生を再開しました"))
        else:
            # 一時停止
            voice_client.pause()
            queue.is_paused = True
            await ctx.send(embed=create_success_embed("⏸ 再生を一時停止しました"))

    # ==================== h!skip - スキップ ====================

    @commands.command(name='skip')
    async def prefix_skip(self, ctx: commands.Context, count: int = 1):
        """
        曲をスキップ（複数曲可能）

        使用例:
            h!skip      # 次の曲へ
            h!skip 3    # 3曲スキップ
        """
        if count < 1:
            await ctx.send(embed=create_error_embed("スキップ数は1以上にしてください"))
            return

        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        voice_client = ctx.guild.voice_client

        if not voice_client or not voice_client.is_playing():
            await ctx.send(embed=create_error_embed("再生中の曲がありません"))
            return

        queue = music_cog.get_queue(ctx.guild.id)

        # スキップ処理
        for _ in range(count):
            if queue.queue:
                queue.queue.pop(0)

        # 現在の曲を停止（次の曲が再生される）
        voice_client.stop()

        if count == 1:
            await ctx.send(embed=create_success_embed("⏭ 次の曲へスキップしました"))
        else:
            await ctx.send(embed=create_success_embed(f"⏭ {count}曲スキップしました"))

    # ==================== h!vol - 音量調整 ====================

    @commands.command(name='vol')
    async def prefix_vol(self, ctx: commands.Context, volume: str = None):
        """
        音量を調整（+/- で相対的に調整）

        使用例:
            h!vol +10   # 10上げる
            h!vol -5    # 5下げる
            h!vol 50    # 50に設定
        """
        if not volume:
            await ctx.send(embed=create_error_embed(
                "使用例",
                "h!vol [+/-数字]\n"
                "例: h!vol +10（10上げる）\n"
                "例: h!vol -5（5下げる）"
            ))
            return

        music_cog = self._get_music_cog()
        if not music_cog:
            await ctx.send(embed=create_error_embed("エラー", "Music Cog が見つかりません"))
            return

        voice_client = ctx.guild.voice_client

        if not voice_client or not voice_client.source:
            await ctx.send(embed=create_error_embed("再生中の曲がありません"))
            return

        try:
            # 現在の音量を取得
            current_volume = voice_client.source.volume * 100

            if volume.startswith('+') or volume.startswith('-'):
                # 相対的に調整
                change = int(volume)
                new_volume = current_volume + change
            else:
                # 絶対値で設定
                new_volume = int(volume)

            # 0-100の範囲に制限
            new_volume = max(0, min(100, new_volume))

            # 音量を設定
            voice_client.source.volume = new_volume / 100

            await ctx.send(embed=create_success_embed(
                "🔊 音量を調整しました",
                f"音量: **{int(new_volume)}%**"
            ))

        except ValueError:
            await ctx.send(embed=create_error_embed(
                "無効な値",
                "数値を指定してください\n"
                "例: h!vol +10"
            ))


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicPrefix(bot))
