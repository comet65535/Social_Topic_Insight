from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import Field
from .base import MongoModel, PyObjectId

class SocialPost(MongoModel):
    # --- 1. 爬虫原始数据 (必须存在) ---
    platform: str            # weibo, douyin, bilibili
    post_id: str             # 平台唯一ID (如 wb_123456)
    url: str
    content: str
    publish_time: datetime
    crawl_time: datetime = Field(default_factory=datetime.now)
    
    author_info: Dict[str, Any] = Field(default_factory=dict) 
    # 例如: {"user_id": "u1", "nickname": "xx", "location": "广东"}
    
    metrics: Dict[str, int] = Field(default_factory=lambda: {"likes": 0, "comments": 0, "shares": 0})
    ip_location: Optional[str] = None

    # --- 2. AI 分析回填数据 (Optional, 初始为 None) ---
    process_status: int = 0  # 0:未处理, 1:已完成, -1:失败
    
    clean_content: Optional[str] = None
    sentiment_score: Optional[float] = None
    keywords: List[str] = Field(default_factory=list)
    
    # 向量数据 (通常不直接展示给前端，但库里要有)
    embedding: Optional[List[float]] = None
    
    # 外键：指向 Topic 表
    topic_ref_id: Optional[PyObjectId] = None

    class Config:
        # 指定 MongoDB 集合名称 (仅作记录，实际在 DB层调用)
        collection_name = "social_posts"