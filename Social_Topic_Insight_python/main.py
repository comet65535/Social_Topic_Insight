import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import db
from modules.api.router import api_router
from worker import main as worker_main


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    yield


# Keep API app for debugging, but production entry now defaults to worker mode.
app = FastAPI(title="Social Topic Insight", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")


def run_api() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    # Default mode is worker so `python main.py` will consume task.queue.
    # Set PYTHON_ENTRY_MODE=api only when you explicitly need FastAPI debug routes.
    entry_mode = os.getenv("PYTHON_ENTRY_MODE", "worker").strip().lower()
    if entry_mode == "api":
        run_api()
    else:
        worker_main()
