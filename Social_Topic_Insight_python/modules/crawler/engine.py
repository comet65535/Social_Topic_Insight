import random
import time
import traceback
from datetime import datetime

from bson import ObjectId

from core.database import db
from core.logger import logger
from modules.analysis.manager import AnalysisManager
from . import config as crawler_config
from .factory import CrawlerFactory


class CrawlerEngine:
    @staticmethod
    def update_task_status(task_id, status, log=None):
        """Update task status in MongoDB."""
        if not task_id:
            return

        try:
            collection = db.get_collection("crawler_tasks")
            update_data = {"status": status}
            if log:
                update_data["log"] = log

            if status in {"completed", "failed"}:
                update_data["finished_time"] = datetime.now()

            collection.update_one({"_id": ObjectId(task_id)}, {"$set": update_data})
        except Exception as ex:
            logger.error(f"Failed to update task status: {ex}")

    @classmethod
    def run(cls, task_config: dict):
        """Run crawler + analysis pipeline for one MQ task."""
        mode = task_config.get("mode", "hot_list")
        platforms = task_config.get("platforms", [])
        keywords_config = task_config.get("keywords", [])
        task_id = task_config.get("task_id")

        logger.info(f"=== Starting Crawler Task {task_id} [Mode: {mode}] ===")
        cls.update_task_status(task_id, "running", log="Task initialized")

        try:
            for platform_name in platforms:
                cls.update_task_status(task_id, "running", log=f"Crawling platform: {platform_name}")

                try:
                    logger.info(f">>> Init Spider: {platform_name}")
                    spider = CrawlerFactory.create_crawler(platform_name)
                    spider.current_task_id = task_id

                    if mode == "hot_list":
                        hot_list = spider.get_hot_search_list()
                        if not hot_list:
                            logger.warning(f"[{platform_name}] No hot list found.")
                            continue

                        targets = hot_list[:7]
                        if len(hot_list) > 8:
                            targets.extend(random.sample(hot_list[7:], 3))

                        for i, keyword in enumerate(targets):
                            spider.crawl(keyword, sort_type="hot")
                            if i % 5 == 0:
                                cls.update_task_status(task_id, "running", log=f"[{platform_name}] Crawling: {keyword}")

                            if platform_name == "douyin":
                                time.sleep(random.uniform(6, 10))
                            else:
                                time.sleep(random.uniform(2, 3))

                    elif mode == "prediction":
                        if keywords_config:
                            targets = keywords_config
                            logger.info(f"User Keywords: {targets}")
                        else:
                            targets = crawler_config.get_smart_seeds(count=3)
                            logger.info(f"Smart Seeds: {targets}")

                        for kw in targets:
                            spider.crawl(kw, sort_type="time")
                            time.sleep(random.uniform(3, 6))

                    if hasattr(spider, "close"):
                        spider.close()

                except Exception as ex:
                    err_msg = f"[{platform_name}] Error: {str(ex)}"
                    logger.error(err_msg)
                    traceback.print_exc()
                    cls.update_task_status(task_id, "running", log=err_msg)

            logger.info("=== Crawler Stage Completed ===")
            cls.update_task_status(task_id, "running", log="Crawling done, start cleaning and clustering")

            try:
                manager = AnalysisManager()
                manager.run_full_pipeline(task_id=task_id)

                logger.info("=== Auto Analysis Completed ===")
                cls.update_task_status(task_id, "clustered", log="Clustering done, waiting Java summary stage")
            except Exception as ex:
                logger.error(f"Auto Analysis Failed: {ex}")
                cls.update_task_status(task_id, "failed", log=f"Clustering failed: {str(ex)}")

        except Exception as ex:
            logger.critical(f"Task Failed: {ex}")
            traceback.print_exc()
            cls.update_task_status(task_id, "failed", log=f"Terminated: {str(ex)}")
