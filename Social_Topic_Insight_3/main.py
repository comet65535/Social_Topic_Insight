from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager # 新增导入
from core.database import db
from modules.api.router import api_router

# 定义生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    print(">>> 系统正在启动，连接数据库...")
    db.connect()
    yield
    # 关闭时执行 (如果有连接池关闭逻辑写在这里)
    print(">>> 系统正在关闭...")

# 在初始化时传入 lifespan
app = FastAPI(title="Social Topic Insight", lifespan=lifespan)

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)