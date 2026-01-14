from pymongo import MongoClient
from .config import settings

class MongoDB:
    client: MongoClient = None
    db = None

    @classmethod
    def connect(cls):
        if cls.client is None:
            cls.client = MongoClient(settings.MONGO_URI)
            cls.db = cls.client[settings.DB_NAME]
            print("================ MongoDB 连接成功 ===========")

    @classmethod
    def get_collection(cls, collection_name):
        return cls.db[collection_name]

# 方便导入的实例
db = MongoDB