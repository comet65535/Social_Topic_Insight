import os
from pathlib import Path
from dotenv import load_dotenv

# 固定从项目根目录加载 .env，避免因启动目录不同导致配置丢失
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


class Settings:
    # Database
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "social_media_analysis")

    # NLP Model
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")

    # Proxy
    PROXY_URL = os.getenv("PROXY_URL", "")

    # Spider
    WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "")

    # RabbitMQ
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
    # 同时兼容 RABBITMQ_USERNAME 与 RABBITMQ_USER 两套命名，避免环境变量不一致导致消费者掉线
    RABBITMQ_USER = os.getenv("RABBITMQ_USERNAME", os.getenv("RABBITMQ_USER", "guest"))
    RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", os.getenv("RABBITMQ_PASS", "guest"))
    RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

    TASK_EXCHANGE = os.getenv("TASK_EXCHANGE", "task.exchange")
    TASK_QUEUE = os.getenv("TASK_QUEUE", "task.queue")
    TASK_ROUTING_KEY = os.getenv("TASK_ROUTING_KEY", "task.routing")

    CLUSTER_EXCHANGE = os.getenv("CLUSTER_EXCHANGE", "cluster.exchange")
    CLUSTER_DONE_ROUTING_KEY = os.getenv("CLUSTER_DONE_ROUTING_KEY", "cluster.done")


settings = Settings()
