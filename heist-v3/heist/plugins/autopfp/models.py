from asyncpg import Pool
from typing import List, Optional
from datetime import datetime

class AutoPFPConfig:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def setup_tables(self):
        await self.pool.execute("""
            CREATE SCHEMA IF NOT EXISTS autopfp;
            
            CREATE TABLE IF NOT EXISTS autopfp.config (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                keyword TEXT NOT NULL,
                channels BIGINT[] DEFAULT '{}',
                enabled BOOLEAN DEFAULT TRUE,
                interval_minutes INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id, keyword)
            );
            
            CREATE TABLE IF NOT EXISTS autopfp.used_images (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                keyword TEXT NOT NULL,
                image_url TEXT NOT NULL,
                used_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id, keyword, image_url)
            );
            
            CREATE TABLE IF NOT EXISTS autopfp.pagination (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                keyword TEXT NOT NULL,
                bookmark TEXT,
                page_number INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id, keyword)
            );
            
            CREATE INDEX IF NOT EXISTS idx_autopfp_config_enabled 
            ON autopfp.config (enabled) WHERE enabled = TRUE;
            
            CREATE INDEX IF NOT EXISTS idx_autopfp_used_images_user 
            ON autopfp.used_images (guild_id, user_id, keyword);
        """)

    async def add_config(self, guild_id: int, user_id: int, keyword: str, 
                        channels: List[int] = None) -> bool:
        try:
            await self.pool.execute("""
                INSERT INTO autopfp.config (guild_id, user_id, keyword, channels)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id, keyword) 
                DO UPDATE SET channels = $4, enabled = TRUE
            """, guild_id, user_id, keyword, channels or [])
            return True
        except:
            return False

    async def get_configs(self, guild_id: int, user_id: int) -> List[dict]:
        return await self.pool.fetch("""
            SELECT * FROM autopfp.config 
            WHERE guild_id = $1 AND user_id = $2
        """, guild_id, user_id)
    
    async def get_config(self, guild_id: int, user_id: int, keyword: str) -> Optional[dict]:
        return await self.pool.fetchrow("""
            SELECT * FROM autopfp.config 
            WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
        """, guild_id, user_id, keyword)

    async def get_active_configs(self) -> List[dict]:
        return await self.pool.fetch("""
            SELECT * FROM autopfp.config WHERE enabled = TRUE
        """)

    async def toggle_config(self, guild_id: int, user_id: int, keyword: str):
        result = await self.pool.fetchval("""
            UPDATE autopfp.config 
            SET enabled = NOT enabled 
            WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
            RETURNING enabled
        """, guild_id, user_id, keyword)
        return result

    async def remove_config(self, guild_id: int, user_id: int, keyword: str = None) -> bool:
        if keyword:
            result = await self.pool.execute("""
                DELETE FROM autopfp.config 
                WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
            """, guild_id, user_id, keyword)
        else:
            result = await self.pool.execute("""
                DELETE FROM autopfp.config 
                WHERE guild_id = $1 AND user_id = $2
            """, guild_id, user_id)
        return result != "DELETE 0"

    async def add_used_image(self, guild_id: int, user_id: int, keyword: str, image_url: str):
        await self.pool.execute("""
            INSERT INTO autopfp.used_images (guild_id, user_id, keyword, image_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
        """, guild_id, user_id, keyword, image_url)

    async def is_image_used(self, guild_id: int, user_id: int, keyword: str, image_url: str) -> bool:
        result = await self.pool.fetchval("""
            SELECT 1 FROM autopfp.used_images 
            WHERE guild_id = $1 AND user_id = $2 AND keyword = $3 AND image_url = $4
        """, guild_id, user_id, keyword, image_url)
        return result is not None

    async def cleanup_old_images(self, days: int = 30):
        await self.pool.execute("""
            DELETE FROM autopfp.used_images 
            WHERE used_at < NOW() - INTERVAL '%s days'
        """, days)

    async def get_pagination(self, guild_id: int, user_id: int, keyword: str) -> Optional[dict]:
        return await self.pool.fetchrow("""
            SELECT * FROM autopfp.pagination 
            WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
        """, guild_id, user_id, keyword)

    async def update_pagination(self, guild_id: int, user_id: int, keyword: str, bookmark: str, page_number: int):
        await self.pool.execute("""
            INSERT INTO autopfp.pagination (guild_id, user_id, keyword, bookmark, page_number)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id, keyword)
            DO UPDATE SET bookmark = $4, page_number = $5, updated_at = NOW()
        """, guild_id, user_id, keyword, bookmark, page_number)

    async def reset_pagination(self, guild_id: int, user_id: int, keyword: str = None):
        if keyword:
            await self.pool.execute("""
                DELETE FROM autopfp.pagination 
                WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
            """, guild_id, user_id, keyword)
        else:
            await self.pool.execute("""
                DELETE FROM autopfp.pagination 
                WHERE guild_id = $1 AND user_id = $2
            """, guild_id, user_id)