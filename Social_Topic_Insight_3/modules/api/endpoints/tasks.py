from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import List
from bson import ObjectId
from core.database import db
from models.task import CrawlerTask
from modules.crawler.engine import CrawlerEngine
from modules.api.utils import resp_200, resp_400

router = APIRouter()

@router.get("", response_model=dict)
async def get_tasks():
    """获取任务列表"""
    collection = db.get_collection("crawler_tasks")
    cursor = collection.find().sort("create_time", -1).limit(20)
    tasks = []
    for doc in cursor:
        # 【核心修改】把 by_alias=True 改为 by_alias=False
        # by_alias=True  -> 返回 {"_id": "..."}
        # by_alias=False -> 返回 {"id": "..."}  <-- 前端需要这个
        tasks.append(CrawlerTask(**doc).model_dump(by_alias=False))
    
    return resp_200(data=tasks)

@router.post("", response_model=dict)
async def create_task(task_in: CrawlerTask, bg_tasks: BackgroundTasks):
    """创建并启动新任务"""
    collection = db.get_collection("crawler_tasks")
    
    # 1. 完善初始状态
    task_data = task_in.model_dump(exclude={"id"}) # 排除 id 让 mongo 自动生成
    task_data["status"] = "running"
    task_data["progress"] = 0
    task_data["log"] = "任务已提交，等待执行..."
    
    # 2. 入库
    result = collection.insert_one(task_data)
    new_task_id = str(result.inserted_id)
    
    # 3. 构造后台任务配置
    crawler_config = {
        "task_id": new_task_id,
        "platforms": task_in.platforms,
        "mode": task_in.mode,
        "keywords": task_in.keywords
    }
    
    # 4. 触发后台爬虫
    bg_tasks.add_task(CrawlerEngine.run, crawler_config)
    
    return resp_200(data={"task_id": new_task_id}, msg="任务已启动")

@router.delete("/{task_id}", response_model=dict)
async def delete_task(task_id: str):
    """删除任务"""
    collection = db.get_collection("crawler_tasks")
    result = collection.delete_one({"_id": ObjectId(task_id)})
    
    if result.deleted_count == 1:
        return resp_200(msg="删除成功")
    else:
        return resp_400(msg="任务不存在")