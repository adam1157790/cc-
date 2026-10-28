"""文生图独立异步 worker：内存队列 + 并发上限，与视频 worker 互不影响。

图片生成为同步接口（数秒~1分钟），流程比视频简单：提交 → 下载落盘 → 完成。
沿用视频 worker 的恢复逻辑：重启后 pending/running 任务自动重新入队。
"""
import asyncio
import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import select

from ..database import SessionLocal
from ..models import ImageTask

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
IMAGES_DIR = DATA_DIR / "images"

# 独立队列（在 main.py 的 lifespan 中启动）
queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None


def new_image_task_id() -> str:
    return "img" + uuid.uuid4().hex[:13]


async def enqueue_image(task_id: str) -> None:
    assert queue is not None, "image worker 未启动"
    await queue.put(task_id)


async def image_worker_loop(concurrency: int) -> None:
    global queue
    queue = asyncio.Queue()
    sem = asyncio.Semaphore(concurrency)

    # 启动恢复：pending/running 重新入队
    async with SessionLocal() as db:
        rows = await db.scalars(select(ImageTask).where(ImageTask.status.in_(("pending", "running"))))
        for t in rows:
            await queue.put(t.id)
            if t.status == "running":
                t.status = "pending"
                t.progress = 0
        await db.commit()

    while True:
        task_id = await queue.get()
        asyncio.create_task(_run_one(task_id, sem))
        queue.task_done()


async def _run_one(task_id: str, sem: asyncio.Semaphore) -> None:
    async with sem:
        try:
            await _process(task_id)
        except Exception as e:  # noqa: BLE001
            await _fail(task_id, f"内部错误: {e}")


async def _fail(task_id: str, message: str) -> None:
    async with SessionLocal() as db:
        task = await db.get(ImageTask, task_id)
        if task is None or task.status in ("succeeded", "failed", "canceled"):
            return
        task.status = "failed"
        task.error = message
        task.finished_at = datetime.now(timezone.utc)
        await db.commit()


async def _process(task_id: str) -> None:
    from ..providers.image_base import get_image_provider

    async with SessionLocal() as db:
        task = await db.get(ImageTask, task_id)
        if task is None:
            return
        if task.status in ("succeeded", "failed", "canceled"):
            return
        task.status = "running"
        task.progress = 20
        await db.commit()
        snapshot = {
            "provider": task.provider,
            "prompt": task.optimized_prompt or task.prompt,
            "size": task.size,
            "seed": task.seed,
            "guidance": task.guidance,
            "ref_image_path": task.ref_image_path,
        }

    provider = get_image_provider(snapshot["provider"])
    result = await provider.generate(
        snapshot["prompt"],
        size=snapshot["size"],
        seed=snapshot["seed"],
        guidance=snapshot["guidance"],
        ref_image_path=snapshot["ref_image_path"],
    )
    if not result.image_url:
        await _fail(task_id, "引擎未返回图片")
        return
    await _finalize(task_id, result.image_url)


async def _finalize(task_id: str, image_url: str) -> None:
    """下载/解码落盘 → 更新状态（URL 有效期短，必须立即落盘）"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGES_DIR / f"{task_id}.png"

    if image_url.startswith("data:"):
        b64 = image_url.split(",", 1)[1]
        image_path.write_bytes(base64.b64decode(b64))
    else:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(image_url)
            if resp.status_code >= 400:
                await _fail(task_id, f"图片下载失败 HTTP {resp.status_code}")
                return
            image_path.write_bytes(resp.content)

    async with SessionLocal() as db:
        task = await db.get(ImageTask, task_id)
        if task is None or task.status == "canceled":
            image_path.unlink(missing_ok=True)
            return
        task.status = "succeeded"
        task.progress = 100
        task.image_path = str(image_path)
        task.finished_at = datetime.now(timezone.utc)
        await db.commit()
