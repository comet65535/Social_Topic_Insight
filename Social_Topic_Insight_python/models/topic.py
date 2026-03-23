from typing import List, Dict, Optional
from datetime import datetime
from pydantic import Field
from .base import MongoModel

class AnalyzedTopic(MongoModel):
    name: str                        # 话题名称
    keywords: List[str]              # 核心关键词
    
    # --- 统计指标 ---
    total_heat: int = 0
    post_count: int = 0
    avg_sentiment: float = 0.0
    
    # --- 生命周期 ---
    first_occur_time: datetime
    last_active_time: datetime
    is_burst: bool = False           # 是否突发
    
    rank_change: int = 0             # 排名变化
    
    # --- 可视化支持 ---
    # 关联话题 (图谱边)
    related_topics: List[Dict] = Field(default_factory=list) 
    # 结构: [{"topic_id": "xxx", "similarity": 0.85}]
    
    # 地域分布
    geo_distribution: List[Dict] = Field(default_factory=list)
    # 结构: [{"name": "广东", "value": 500}]

    class Config:
        collection_name = "analyzed_topics"