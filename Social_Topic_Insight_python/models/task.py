from typing import List, Dict, Optional
from datetime import datetime
from pydantic import Field
from .base import MongoModel

class CrawlerTask(MongoModel):
    name: str
    platforms: List[str]            # ["weibo", "douyin"]
    keywords: List[str] = []        # 预测模式下的关键词
    mode: str = "hot_list"          # hot_list 或 prediction
    
    date_range: Dict[str, Optional[datetime]] = Field(default_factory=dict)
    
    status: str = "pending"         # pending, running, completed, failed
    progress: int = 0
    
    create_time: datetime = Field(default_factory=datetime.now)
    finished_time: Optional[datetime] = None
    
    log: str = ""                   # 实时日志
    result_summary: Dict = Field(default_factory=dict)

    class Config:
        collection_name = "crawler_tasks"