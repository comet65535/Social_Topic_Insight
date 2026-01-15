import sys
import os
import time

# 1. 将当前目录加入 Python 搜索路径，防止报错 ModuleNotFoundError
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import db
from core.logger import logger
from modules.analysis.clustering import ClusterEngine
from modules.analysis.manager import AnalysisManager

def test_only_clustering():
    """
    场景 A: 数据库里已经有 process_status=1 且 embedding 有值的帖子。
    只运行聚类 + LLM 命名 + 趋势计算。
    """
    print(">>> [测试模式] 正在初始化数据库连接...")
    db.connect()

    # 检查一下有没有数据
    count = db.get_collection("social_posts").count_documents({
        "process_status": 1, 
        "embedding": {"$ne": None}
    })
    print(f">>> [数据检查] 发现 {count} 条已向量化(Embedded)的帖子可供聚类。")

    if count < 5:
        print("!!! 警告：数据量过少，聚类可能效果不佳或报错。建议先跑爬虫或运行全流程测试。")

    print(">>> [开始] 实例化 ClusterEngine...")
    engine = ClusterEngine()
    
    print(">>> [运行] 开始执行 run_clustering()...")
    try:
        engine.run_clustering()
        print(">>> [成功] 聚类任务执行完毕！请查看数据库 analyzed_topics 表。")
    except Exception as e:
        logger.error(f"聚类测试报错: {e}")
        import traceback
        traceback.print_exc()

def test_full_pipeline():
    """
    场景 B: 数据库里只有原始爬虫数据 (process_status=0)。
    需要先清洗 -> NLP向量化 -> 然后再聚类。
    """
    print(">>> [测试模式] 运行全流程分析 (清洗+向量化+聚类)...")
    db.connect()
    
    manager = AnalysisManager()
    
    # 1. 先处理原始数据 (清洗 + 向量化)
    # batch_size 可以设大一点加快速度
    manager.process_raw_posts(batch_size=100) 
    
    # 2. 再执行聚类
    manager.run_topic_clustering()

if __name__ == "__main__":
    # --- 请根据你的需求取消注释其中一个 ---

    # 选项 1: 只测聚类 (前提：你之前已经跑过 process_raw_posts，或者数据里已经有向量了)
    test_only_clustering()

    # 选项 2: 全流程 (如果你的帖子是刚爬下来的，还没生成向量，用这个)
    # test_full_pipeline()