"""
複数のソースから歌詞を検索するユーティリティ
"""

import asyncio
import re
from typing import Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Genius APIのインポート（オプション）
try:
    from lyricsgenius import Genius
    GENIUS_AVAILABLE = True
except ImportError:
    GENIUS_AVAILABLE = False

# BeautifulSoupのインポート
try:
    import requests
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False


class LyricsSearcher:
    """複数のソースから歌詞を検索"""

    def __init__(self, genius_token: Optional[str] = None):
        self.genius = None
        if genius_token and GENIUS_AVAILABLE:
            try:
                self.genius = Genius(genius_token, timeout=10, retries=3)
            except Exception as e:
                logger.warning(f"Genius initialization failed: {str(e)}")

    async def search(self, title: str, artist: Optional[str] = None) -> Tuple[Optional[str], str]:
        """
        複数のソースから歌詞を検索

        Args:
            title: 曲のタイトル
            artist: アーティスト名（オプション）

        Returns:
            (歌詞, ソース名) のタプル
        """
        loop = asyncio.get_event_loop()

        # 1. Genius APIで検索
        if self.genius:
            try:
                logger.info(f"Searching Genius for: {title} by {artist or 'Unknown'}")
                song = await loop.run_in_executor(
                    None,
                    lambda: self.genius.search_song(title, artist)
                )

                if song and song.lyrics:
                    return (song.lyrics, "Genius")
            except Exception as e:
                logger.warning(f"Genius search failed: {str(e)}")

        # 2. uta-netで検索
        if BEAUTIFULSOUP_AVAILABLE:
            try:
                logger.info(f"Searching uta-net for: {title} by {artist or 'Unknown'}")
                lyrics = await self._search_utanet(title, artist, loop)
                if lyrics:
                    return (lyrics, "uta-net")
            except Exception as e:
                logger.warning(f"uta-net search failed: {str(e)}")

        # 見つからなかった
        return (None, "")

    async def _search_utanet(self, title: str, artist: Optional[str], loop) -> Optional[str]:
        """uta-netから歌詞を検索"""
        try:
            # uta-netの検索ページ
            search_url = "https://www.uta-net.com/search/"

            # 検索パラメータ
            query = f"{artist} {title}" if artist else title
            params = {"kashi": query}

            # 検索実行（非同期）
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(search_url, params=params, timeout=10)
            )
            response.encoding = 'utf-8'

            if response.status_code != 200:
                logger.warning(f"uta-net search returned status {response.status_code}")
                return None

            # 検索結果をパース
            soup = BeautifulSoup(response.text, 'html.parser')

            # 検索結果リンクを取得
            song_link = None
            for link in soup.find_all('a', href=True):
                if '/song/' in link['href']:
                    song_link = link['href']
                    break

            if not song_link:
                logger.info("No song found on uta-net")
                return None

            # 相対URLを絶対URLに変換
            if song_link.startswith('/'):
                song_link = f"https://www.uta-net.com{song_link}"

            logger.info(f"Found song on uta-net: {song_link}")

            # 歌詞ページを取得
            lyrics_response = await loop.run_in_executor(
                None,
                lambda: requests.get(song_link, timeout=10)
            )
            lyrics_response.encoding = 'utf-8'

            if lyrics_response.status_code != 200:
                logger.warning(f"uta-net lyrics page returned status {lyrics_response.status_code}")
                return None

            # 歌詞をパース
            lyrics_soup = BeautifulSoup(lyrics_response.text, 'html.parser')

            # 歌詞テキストを取得（kashi_kuクラスの要素）
            lyrics_div = lyrics_soup.find('div', class_='kashi_ku')

            if not lyrics_div:
                logger.warning("Could not find lyrics content on uta-net")
                return None

            # 歌詞テキストを抽出（<br>をを\nに変換）
            lyrics_text = str(lyrics_div)
            lyrics_text = re.sub(r'<br\s*/?>', '\n', lyrics_text)

            # HTMLタグを削除
            lyrics_text = re.sub(r'<[^>]+>', '', lyrics_text)

            # HTMLエンティティをデコード
            from html import unescape
            lyrics_text = unescape(lyrics_text)

            # 余分な空白を削除
            lyrics_text = lyrics_text.strip()

            if lyrics_text:
                return lyrics_text

            logger.warning("Extracted lyrics are empty")
            return None

        except Exception as e:
            logger.error(f"Error scraping uta-net: {str(e)}")
            return None
