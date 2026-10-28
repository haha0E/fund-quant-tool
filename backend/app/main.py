"""FastAPI 入口。启动：uv run uvicorn app.main:app --port 8000（在 backend/ 目录下）。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import REPO_ROOT
from .db import init_db
from .routers import funds, refresh

# 生产态构建产物（npm run build 产出；dist 不入 git，未构建时仅提供 API）
DIST_DIR = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="基金研究工作台", version="0.1.0", lifespan=lifespan)

# 前端开发期由 Vite 代理 /api，CORS 兜底放开本地访问；生产态同源托管无需放宽
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router)
app.include_router(refresh.router)


@app.get("/api/health")
def health():
    from .config import DB_PATH
    from .db import conn

    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM fund").fetchone()[0]
    return {"status": "ok", "db_path": str(DB_PATH), "fund_count": count}


# ---- 生产态静态托管（实现方案 §7：FastAPI 直接托管 frontend/dist，同源免 CORS 放宽）----
# 兜底路由注册在全部 /api 路由之后：未知 /api 路径按 404 处理，不回退页面；
# 其余未命中路径先按静态文件找（resolve 校验防穿越），再回退 index.html（SPA 前端路由）。
if DIST_DIR.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (DIST_DIR / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST_DIR.resolve()):
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
