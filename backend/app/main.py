"""FastAPI 入口：启动时初始化数据库、启动 worker"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import admin, auth, images, storyboards, tasks
from .services import image_worker, worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    worker_task = asyncio.create_task(worker.worker_loop(settings.max_concurrent_tasks))
    # 文生图独立 worker：并发上限单配，与视频队列互不影响
    img_worker_task = asyncio.create_task(image_worker.image_worker_loop(settings.max_concurrent_image_tasks))
    yield
    worker_task.cancel()
    img_worker_task.cancel()


app = FastAPI(title="文生视频创作平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 允许本机 + 任意局域网 IP + 穿透隧道域名（cloudflared / cpolar）
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$|^https?://[a-z0-9-]+\.trycloudflare\.com$|^https?://[a-z0-9-]+\.[a-z0-9-]+\.cpolar\.top$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(images.router)
app.include_router(storyboards.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/config")
async def app_config():
    """前端启动配置：公网 API 地址（cpolar 双隧道时，API 隧道地址动态下发）

    由启动脚本把 cpolar API 隧道地址写到 data/api_tunnel.txt，后端读取下发给前端。
    """
    from pathlib import Path

    api_tunnel = ""
    tunnel_file = Path(__file__).resolve().parent.parent / "data" / "api_tunnel.txt"
    if tunnel_file.exists():
        api_tunnel = tunnel_file.read_text(encoding="utf-8").strip()
    return {"api_base": api_tunnel}
