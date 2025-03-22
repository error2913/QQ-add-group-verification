import aiosqlite
import os

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
        await self.conn.close()
    
    async def init_db(self):
        """初始化数据库"""
        async with self as db:
            await db.conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    group_id INTEGER PRIMARY KEY
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
                await db.conn.execute(
                    "INSERT INTO whitelist VALUES (?)",
                    (group_id,)
                )
                await db.conn.commit()
                return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            print(f"添加白名单失败: {e}")
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
            print(f"移除白名单失败: {e}")
            return False