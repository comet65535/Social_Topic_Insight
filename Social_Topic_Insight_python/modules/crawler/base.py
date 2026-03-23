from abc import ABC, abstractmethod
from pymongo.errors import DuplicateKeyError
from core.database import db
from core.logger import logger

class BaseCrawler(ABC):
    def __init__(self):
        # 通过 core/database.py 获取集合
        # 确保在使用前 db.connect() 已经被 main.py 调用过
        self.collection = db.get_collection('social_posts')
        
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
            # 插入数据
            self.collection.insert_one(data)
            logger.info(f"[Crawler] Saved {data['platform']} - {data['post_id']}")
        except DuplicateKeyError:
            # 重复是正常的，静默处理或 debug 级日志
            # logger.debug(f"[Crawler] Duplicate {data['platform']} - {data['post_id']}")
            pass
        except Exception as e:
            logger.error(f"[Crawler] Save Error: {e}")