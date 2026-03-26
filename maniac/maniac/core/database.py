from motor.motor_asyncio import AsyncIOMotorClient
from .config import Config

class Database:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def connect(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DB]
        print("MongoDB connected successfully")
    
    async def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed")
    
    def __getattr__(self, name):
        return self.db[name]

db = Database()
