import time
from typing import List
from core.database import db
from core.logger import logger
from models.post import SocialPost
from .cleaning import TextCleaner
from .nlp_base import NLPProcessor
from .clustering import ClusterEngine

class AnalysisManager:
    def __init__(self):
        self.nlp = NLPProcessor()
        self.is_running = False

    def process_raw_posts(self, batch_size=50):
        """
        第一阶段：对原始数据进行清洗、NLP提取、向量化
        """
        logger.info("--- [Analysis Task] Starting batch processing ---")
        collection = db.get_collection("social_posts")
        
        processed_count = 0
        
        try:
            while True:
                # 1. 捞取未处理的数据
                cursor = collection.find({"process_status": 0}).limit(batch_size)
                posts_data = list(cursor)
                
                if not posts_data:
                    break
                
                logger.info(f"Processing batch of {len(posts_data)} posts...")
                
                for p_data in posts_data:
                    try:
                        # 转换成 Pydantic 模型方便操作 (可选，也可以直接用 dict)
                        # 注意：直接操作 dict 速度更快，这里为了稳健展示 dict 操作
                        post_id = p_data["_id"]
                        raw_content = p_data.get("content", "")
                        
                        # A. 清洗
                        clean_content = TextCleaner.clean(raw_content)
                        if len(clean_content) < 4:
                            collection.update_one(
                                {"_id": post_id}, 
                                {"$set": {"process_status": -1, "note": "内容过短"}}
                            )
                            continue
                            
                        # B. NLP 处理
                        keywords = self.nlp.get_keywords(clean_content)
                        sentiment = self.nlp.get_sentiment(clean_content)
                        embedding = self.nlp.get_embedding(clean_content)
                        
                        # C. 更新数据库
                        collection.update_one(
                            {"_id": post_id},
                            {"$set": {
                                "clean_content": clean_content,
                                "keywords": keywords,
                                "sentiment_score": sentiment,
                                "embedding": embedding,
                                "process_status": 1, # 第一阶段完成，等待聚类
                                "analyzed_time": datetime.now()
                            }}
                        )
                        processed_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing post {p_data.get('_id')}: {e}")
                        collection.update_one(
                            {"_id": p_data["_id"]},
                            {"$set": {"process_status": -1, "error": str(e)}}
                        )
                
                # 简单的流控
                time.sleep(0.1)
                
        finally:
            logger.info(f"--- [Analysis Task] Finished. Processed {processed_count} posts. ---")

    def run_topic_clustering(self):
        """
        第二阶段：基于已向量化的数据进行聚类
        """
        cluster_engine = ClusterEngine()
        cluster_engine.run_clustering()

    def run_full_pipeline(self):
        """
        全流程快捷入口
        """
        self.is_running = True
        try:
            self.process_raw_posts()
            self.run_topic_clustering()
        finally:
            self.is_running = False

# 导出辅助使用的 datetime，因为上面用到了
from datetime import datetime