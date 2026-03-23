import logging
import sys
import os
from logging.handlers import RotatingFileHandler

# 确保日志目录存在
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(name="SocialInsight"):
    logger = logging.getLogger(name)
    
    # 防止重复添加 Handler (FastAPI reload 时容易出现重复日志)
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)

    # 1. 格式定义
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s'
    )

    # 2. 控制台处理器 (Console Handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 3. 文件处理器 (File Handler) - 按大小轮转 (例如 10MB 一个文件，保留 5 个)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# 导出单例
logger = get_logger()