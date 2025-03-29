import aiosqlite
import os
from config import config
import logging

logger = logging.getLogger(__name__)

# 获取当前模块所在目录
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(DATABASE_DIR, "data.db")

class Database:
    def __init__(self):
        self.white_list_cache: list = None
        self.conn: aiosqlite.Connection = None
    
    async def __aenter__(self):
        self.conn = await aiosqlite.connect(DATABASE_PATH)
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        if self.conn:
            await self.conn.close()
    
    async def init_db(self):
        """初始化数据库"""
        async with self as db:
            await db.conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    group_id INTEGER PRIMARY KEY,
                    threshold INTEGER NOT NULL DEFAULT 5,
                    timeout INTEGER NOT NULL DEFAULT 60
                )
            """)
            await db.conn.commit()
    
    async def get_white_list(self) -> list:
        """获取白名单列表"""
        if self.white_list_cache is None:
            async with self as db:
                cursor = await db.conn.execute("SELECT group_id FROM whitelist")
                self.white_list_cache = [row[0] async for row in cursor]

        return self.white_list_cache
    
    async def add_group(self, group_id: int) -> bool:
        """添加白名单群组"""
        self.white_list_cache = None
        
        try:
            async with self as db:
                threshold = config.level_threshold
                timeout = config.verify_timeout
                await db.conn.execute(
                    "INSERT INTO whitelist (group_id, threshold, timeout) VALUES (?, ?, ?)",
                    (group_id, threshold, timeout)
                )
                await db.conn.commit()
                return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"添加白名单失败: {e}")
            return False
    
    async def remove_group(self, group_id: int) -> bool:
        """移除白名单群组"""
        self.white_list_cache = None
        
        try:
            async with self as db:
                cursor = await db.conn.execute(
                    "DELETE FROM whitelist WHERE group_id=?",
                    (group_id,)
                )
                await db.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"移除白名单失败: {e}")
            return False
        
    async def set_threshold(self, group_id: int, threshold: int) -> bool:
        """设置白名单群组的阈值"""
        self.white_list_cache = None

        try:
            async with self as db:
                await db.conn.execute(
                    "UPDATE whitelist SET threshold=? WHERE group_id=?",
                    (threshold, group_id)
                )
                await db.conn.commit()
                return True
        except Exception as e:
            logger.error(f"设置白名单阈值失败: {e}")
            return False
        
    async def get_threshold(self, group_id: int) -> int:
        """获取白名单群组的阈值"""
        async with self as db:
            cursor = await db.conn.execute(
                "SELECT threshold FROM whitelist WHERE group_id=?",
                (group_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else config.level_threshold

    async def set_timeout(self, group_id: int, timeout: int) -> bool:
        """设置白名单群组的超时时间"""
        self.white_list_cache = None

        try:
            async with self as db:
                await db.conn.execute(
                    "UPDATE whitelist SET timeout=? WHERE group_id=?",
                    (timeout, group_id)
                )
                await db.conn.commit()
                return True
        except Exception as e:
            logger.error(f"设置白名单超时时间失败: {e}")
            return False

    async def get_timeout(self, group_id: int) -> int:
        """获取白名单群组的超时时间"""
        async with self as db:
            cursor = await db.conn.execute(
                "SELECT timeout FROM whitelist WHERE group_id=?",
                (group_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else config.verify_timeout