import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Settings:
    # 1. 数据库配置
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "social_media_analysis")
    
    # 2. 模型配置
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")
    
    # 3. LLM API Keys
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    
    # 4. 代理配置
    PROXY_URL = os.getenv("PROXY_URL", "")

    # 5. 微博配置
    WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "")

    # 检查 Key 是否存在的辅助属性 (可选)
    @property
    def has_llm_keys(self):
        return bool(self.GOOGLE_API_KEY or self.DEEPSEEK_API_KEY)

settings = Settings()