import redis.asyncio as redis
from app.core.config import settings
import logging
import json
from typing import Any, Optional

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis.ping()
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None):
        """Set a key-value pair in Redis"""
        if self.redis:
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            await self.redis.set(key, serialized_value, ex=expire)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis"""
        if self.redis:
            value = await self.redis.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
        return None
    
    async def delete(self, key: str):
        """Delete a key from Redis"""
        if self.redis:
            await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        if self.redis:
            return await self.redis.exists(key)
        return False
    
    async def set_session_data(self, session_id: str, data: dict, expire: int = 3600):
        """Store session data"""
        await self.set(f"session:{session_id}", data, expire)
    
    async def get_session_data(self, session_id: str) -> Optional[dict]:
        """Retrieve session data"""
        return await self.get(f"session:{session_id}")
    
    async def delete_session_data(self, session_id: str):
        """Delete session data"""
        await self.delete(f"session:{session_id}")
    
    async def set_room_state(self, room_id: str, state: dict, expire: int = 7200):
        """Store room state"""
        await self.set(f"room:{room_id}", state, expire)
    
    async def get_room_state(self, room_id: str) -> Optional[dict]:
        """Retrieve room state"""
        return await self.get(f"room:{room_id}")
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

# Global Redis client instance
redis_client = RedisClient()

async def init_redis():
    """Initialize Redis client"""
    await redis_client.init_redis()

async def get_redis() -> RedisClient:
    """Get Redis client instance"""
    return redis_client