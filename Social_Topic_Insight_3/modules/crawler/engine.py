import time
import random
import traceback
from bson import ObjectId
from core.database import db
from core.logger import logger
from .factory import CrawlerFactory
from . import config as crawler_config
from modules.analysis.manager import AnalysisManager 



class CrawlerEngine:
    @staticmethod
    def update_task_status(task_id, status, log=None):
        """更新数据库中的任务状态"""
        if not task_id: return
        try:
            collection = db.get_collection("crawler_tasks")
            update_data = {"status": status}
            if log:
                update_data["log"] = log
            
            if status == "completed" or status == "failed":
                import datetime
                update_data["finished_time"] = datetime.datetime.now()

            collection.update_one(
                {"_id": ObjectId(task_id)}, 
                {"$set": update_data}
            )
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")

    @classmethod
    def run(cls, task_config: dict):
        """
        核心执行逻辑 (在后台线程中运行)
        task_config: 来自 API 或数据库的配置字典
        """
        mode = task_config.get('mode', 'hot_list')
        platforms = task_config.get('platforms', [])
        keywords_config = task_config.get('keywords', [])
        task_id = task_config.get('task_id')

        logger.info(f"=== Starting Crawler Task {task_id} [Mode: {mode}] ===")
        cls.update_task_status(task_id, "running", log="初始化完成，开始采集...")

        try:
            for platform_name in platforms:
                cls.update_task_status(task_id, "running", log=f"正在采集平台: {platform_name}...")
                
                try:
                    logger.info(f">>> Init Spider: {platform_name}")
                    spider = CrawlerFactory.create_crawler(platform_name)
                    
                    # --- 分支 1: 全网热榜模式 ---
                    if mode == 'hot_list':
                        hot_list = spider.get_hot_search_list()
                        if not hot_list:
                            logger.warning(f"[{platform_name}] No hot list found.")
                            continue
                        
                        # 取前15个热词 + 随机5个
                        targets = hot_list[:15]
                        if len(hot_list) > 16:
                            targets.extend(random.sample(hot_list[15:], 5))
                        
                        for i, keyword in enumerate(targets):
                            spider.crawl(keyword, sort_type="hot")
                            
                            # 简单的进度反馈
                            progress = int((i + 1) / len(targets) * 100)
                            # 只要不频繁写库就行
                            if i % 5 == 0: 
                                cls.update_task_status(task_id, "running", log=f"[{platform_name}] 正在抓取: {keyword}")
                            
                            if platform_name == "douyin":
                                time.sleep(random.uniform(6,12))
                            else:
                                time.sleep(random.uniform(2, 4))

                    # --- 分支 2: 热点预测模式 ---
                    elif mode == 'prediction':
                        targets = []
                        if keywords_config:
                            targets = keywords_config
                            logger.info(f"User Keywords: {targets}")
                        else:
                            targets = crawler_config.get_smart_seeds(count=3)
                            logger.info(f"Smart Seeds: {targets}")
                            
                        for kw in targets:
                            spider.crawl(kw, sort_type="time")
                            time.sleep(random.uniform(3, 6))

                    # 关闭资源 (DrissionPage可能需要)
                    if hasattr(spider, 'close'):
                        spider.close()

                except Exception as e:
                    err_msg = f"[{platform_name}] Error: {str(e)}"
                    logger.error(err_msg)
                    traceback.print_exc()
                    cls.update_task_status(task_id, "running", log=err_msg)

            logger.info("=== Task Completed ===")
            cls.update_task_status(task_id, "completed", log="爬虫任务全部完成")

            try:
                # 实例化分析管理器
                manager = AnalysisManager()
                # 运行全流程 (清洗 -> NLP -> 聚类)
                manager.run_full_pipeline()
                
                logger.info("=== Auto Analysis Completed ===")
                # 最终标记为完成
                cls.update_task_status(task_config.get('task_id'), "completed", log="数据处理任务全部完成")
                
            except Exception as e:
                logger.error(f"Auto Analysis Failed: {e}")
                # 注意：虽然分析失败，但爬虫是成功的。
                # 你可以选择标记为 completed 但在 log 里写分析失败，或者标记为 failed
                cls.update_task_status(task_config.get('task_id'), "completed", log=f"爬虫成功，但AI分析出错: {str(e)}")

        except Exception as e:
            logger.critical(f"Task Failed: {e}")
            traceback.print_exc()
            cls.update_task_status(task_id, "failed", log=f"异常终止: {str(e)}")