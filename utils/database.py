import sqlite3
import os
from typing import Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Database:
    """データベース管理クラス"""

    def __init__(self, db_path: str = 'bot_database.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """データベースとテーブルを初期化"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ユーザーレベルテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_levels (
                guild_id TEXT,
                user_id TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')

        # 警告履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def get_user_xp(self, guild_id: str, user_id: str) -> Tuple[int, int, int]:
        """ユーザーのXP、レベル、メッセージ数を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT xp, level, messages FROM user_levels
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))

        result = cursor.fetchone()
        conn.close()

        if result:
            return result
        return (0, 0, 0)

    def add_xp(self, guild_id: str, user_id: str, xp_amount: int) -> Tuple[int, int, bool]:
        """XPを追加し、レベルアップしたかを返す"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        current_xp, current_level, messages = self.get_user_xp(guild_id, user_id)
        new_xp = current_xp + xp_amount
        new_messages = messages + 1

        # レベル計算（必要XP = レベル * 100）
        required_xp = (current_level + 1) * 100
        level_up = False

        if new_xp >= required_xp:
            current_level += 1
            new_xp -= required_xp
            level_up = True

        cursor.execute('''
            INSERT INTO user_levels (guild_id, user_id, xp, level, messages)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                xp = ?,
                level = ?,
                messages = ?
        ''', (guild_id, user_id, new_xp, current_level, new_messages,
              new_xp, current_level, new_messages))

        conn.commit()
        conn.close()

        return (current_level, new_xp, level_up)

    def get_leaderboard(self, guild_id: str, limit: int = 10):
        """サーバーのリーダーボードを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, xp, level, messages
            FROM user_levels
            WHERE guild_id = ?
            ORDER BY level DESC, xp DESC
            LIMIT ?
        ''', (guild_id, limit))

        results = cursor.fetchall()
        conn.close()

        return results

    def add_warning(self, guild_id: str, user_id: str, moderator_id: str, reason: str):
        """警告を追加"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?)
        ''', (guild_id, user_id, moderator_id, reason))

        conn.commit()
        conn.close()
        logger.info(f"Warning added for user {user_id} in guild {guild_id}")

    def get_warnings(self, guild_id: str, user_id: str):
        """ユーザーの警告履歴を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT moderator_id, reason, timestamp
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY timestamp DESC
        ''', (guild_id, user_id))

        results = cursor.fetchall()
        conn.close()

        return results

    def clear_warnings(self, guild_id: str, user_id: str):
        """ユーザーの警告履歴をクリア"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM warnings
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))

        conn.commit()
        conn.close()
        logger.info(f"Warnings cleared for user {user_id} in guild {guild_id}")
