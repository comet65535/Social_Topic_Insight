from abc import ABC, abstractmethod
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from core.database import db
from core.logger import logger

class BaseCrawler(ABC):
    def __init__(self):
        # 通过 core/database.py 获取集合
        # 确保在使用前 db.connect() 已经被 main.py 调用过
        self.collection = db.get_collection('social_posts')
        # 由 CrawlerEngine 在任务开始时注入，确保每条帖子可追溯到任务。
        self.current_task_id = None
        
        # 确保索引存在 (post_id 唯一)
        # 注意：create_index 是幂等的，重复调用没事
        try:
            self.collection.create_index("post_id", unique=True)
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    @abstractmethod
    def crawl(self, keyword, sort_type="hot"):
        """子类必须实现此方法"""
        pass
    
    @abstractmethod
    def get_hot_search_list(self):
        """子类必须实现此方法"""
        pass

    def save_data(self, data: dict):
        """通用保存方法"""
        try:
            payload = dict(data)
            if self.current_task_id:
                payload["task_id"] = str(self.current_task_id)
            if payload.get("crawl_time") is None:
                payload["crawl_time"] = datetime.now()
            # 插入数据
            self.collection.insert_one(payload)
            logger.info(f"[Crawler] Saved {payload['platform']} - {payload['post_id']}")
        except DuplicateKeyError:
            # 遇到重复 post_id 时，不丢弃本次任务上下文：
            # 1) 回写最新 crawl_time/task_id
            # 2) 重置 process_status 触发本轮分析，避免“任务完成但数据不更新”
            self.collection.update_one(
                {"post_id": payload.get("post_id")},
                {"$set": {
                    "content": payload.get("content"),
                    "publish_time": payload.get("publish_time"),
                    "crawl_time": payload.get("crawl_time"),
                    "author_info": payload.get("author_info", {}),
                    "metrics": payload.get("metrics", {}),
                    "ip_location": payload.get("ip_location"),
                    "platform": payload.get("platform"),
                    "url": payload.get("url"),
                    "task_id": payload.get("task_id"),
                    "process_status": 0
                }}
            )
            logger.info(f"[Crawler] Updated duplicate {payload['platform']} - {payload['post_id']}")
        except Exception as e:
            logger.error(f"[Crawler] Save Error: {e}")
