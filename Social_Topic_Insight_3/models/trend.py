from typing import Optional
from pydantic import Field
from .base import MongoModel, PyObjectId

class TopicTrend(MongoModel):
    # 外键
    topic_ref_id: PyObjectId
    
    time_bucket: str                 # 时间切片，如 "2025-01-08 14:00"
    
    heat_value: int
    post_count: int
    sentiment_value: float
    
    representative_post: Optional[str] = None # 存 post_id

    class Config:
        collection_name = "topic_trends"