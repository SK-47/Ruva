from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None

db = Database()

async def get_database() -> AsyncIOMotorDatabase:
    return db.database

async def init_db():
    """Initialize database connection"""
    try:
        db.client = AsyncIOMotorClient(settings.MONGODB_URL)
        db.database = db.client[settings.DATABASE_NAME]
        
        # Test the connection
        await db.client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
        # Create indexes
        await create_indexes()
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def create_indexes():
    """Create database indexes for better performance"""
    try:
        # Room indexes
        await db.database.rooms.create_index("id", unique=True)
        await db.database.rooms.create_index("isActive")
        
        # Session indexes
        await db.database.sessions.create_index("id", unique=True)
        await db.database.sessions.create_index("roomId")
        await db.database.sessions.create_index("startTime")
        
        # Speech analysis indexes
        await db.database.speech_analysis.create_index("sessionId")
        await db.database.speech_analysis.create_index("participantId")
        await db.database.speech_analysis.create_index("timestamp")

        # User indexes
        await db.database.users.create_index("email", unique=True)
        await db.database.users.create_index("username", unique=True)
        
        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")

async def close_db():
    """Close database connection"""
    if db.client:
        db.client.close()
        logger.info("Database connection closed")