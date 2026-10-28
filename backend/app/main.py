"""FastAPI 入口。启动：uv run uvicorn app.main:app --port 8000（在 backend/ 目录下）。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import funds


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="基金研究工作台", version="0.1.0", lifespan=lifespan)

# 前端开发期由 Vite 代理 /api，CORS 兜底放开本地访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router)


@app.get("/api/health")
def health():
    from .config import DB_PATH
    from .db import conn

    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM fund").fetchone()[0]
    return {"status": "ok", "db_path": str(DB_PATH), "fund_count": count}
