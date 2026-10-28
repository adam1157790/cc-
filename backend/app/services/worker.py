"""异步任务 worker：内存队列 + 并发上限，负责提交→轮询→下载→抽帧全流程。

为什么不用 Celery/Redis：单机自用+小规模共用场景，进程内 asyncio 队列
免部署、免运维，重启后 pending 任务自动重新入队（见 main.py 的恢复逻辑）。
"""
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from ..database import SessionLocal
from ..models import Storyboard, Task
from . import video_utils

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
VIDEOS_DIR = DATA_DIR / "videos"
COVERS_DIR = DATA_DIR / "covers"

# 全局队列与并发闸门（在 main.py 的 lifespan 中启动）
queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_active: set[str] = set()  # 正在处理的任务ID


def new_task_id() -> str:
    return uuid.uuid4().hex[:16]


async def enqueue(task_id: str) -> None:
    assert queue is not None, "worker 未启动"
    await queue.put(task_id)


async def worker_loop(concurrency: int) -> None:
    """主循环：从队列取任务，最多同时跑 concurrency 个"""
    global queue
    queue = asyncio.Queue()
    sem = asyncio.Semaphore(concurrency)

    # 启动时恢复：上次进程退出时仍在 pending/running 的任务重新入队
    async with SessionLocal() as db:
        rows = await db.scalars(select(Task).where(Task.status.in_(("pending", "running"))))
        for t in rows:
            await queue.put(t.id)
            # running 的任务需要重新提交（provider侧ID可能已失效），标记回 pending
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
        _active.add(task_id)
        try:
            await _process(task_id)
        except Exception as e:  # noqa: BLE001
            await _fail(task_id, f"内部错误: {e}")
        finally:
            _active.discard(task_id)


async def _fail(task_id: str, message: str) -> None:
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None or task.status in ("succeeded", "failed", "canceled"):
            return
        task.status = "failed"
        task.error = message
        task.finished_at = datetime.now(timezone.utc)
        await db.commit()
        if task.storyboard_id:
            await _sync_storyboard(db, task.storyboard_id)


async def _process(task_id: str) -> None:
    from ..providers import get_provider

    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return
        if task.status in ("succeeded", "failed", "canceled"):
            return
        task.status = "running"
        task.progress = 5
        await db.commit()
        snapshot = _snapshot(task)

    provider = get_provider(snapshot["provider"])
    # 1. 提交
    try:
        result = await provider.submit(
            snapshot["optimized_prompt"] or snapshot["prompt"],
            duration=snapshot["duration"],
            aspect_ratio=snapshot["aspect_ratio"],
            seed=snapshot["seed"],
            image_path=snapshot["image_path"],
        )
    except Exception as e:  # noqa: BLE001
        await _fail(task_id, f"提交失败: {e}")
        return

    async with SessionLocal() as db:
        t = await db.get(Task, task_id)
        t.provider_task_id = result.provider_task_id
        await db.commit()

    if result.video_url:
        await _finalize(task_id, result.video_url)
        return

    # 2. 轮询（5秒间隔，总上限25分钟）
    import time

    deadline = time.monotonic() + 25 * 60
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        try:
            poll = await provider.poll(result.provider_task_id)
        except Exception as e:  # noqa: BLE001
            poll = type("P", (), {"status": "running", "progress": 50})()  # 网络抖动先容忍
            _ = e
        if poll.status == "succeeded":
            await _finalize(task_id, poll.video_url)
            return
        if poll.status == "failed":
            await _fail(task_id, poll.error or "生成失败")
            return
        async with SessionLocal() as db:
            t = await db.get(Task, task_id)
            if t is None or t.status == "canceled":
                return  # 用户已取消
            t.progress = max(t.progress, poll.progress)
            await db.commit()
    await _fail(task_id, "生成超时（25分钟）")


async def _finalize(task_id: str, video_url: str) -> None:
    """下载 → 抽封面 → 更新状态 → 同步分镜聚合状态"""
    video_path = VIDEOS_DIR / f"{task_id}.mp4"
    await video_utils.download_video(video_url, video_path)

    cover_path = COVERS_DIR / f"{task_id}.jpg"
    try:
        await asyncio.to_thread(video_utils.extract_cover, video_path, cover_path)
    except Exception:  # noqa: BLE001
        cover_path = None  # 封面失败不影响任务成功

    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None or task.status == "canceled":
            video_path.unlink(missing_ok=True)  # 已取消，清理
            return
        task.status = "succeeded"
        task.progress = 100
        task.video_path = str(video_path)
        task.cover_path = str(cover_path) if cover_path else None
        task.finished_at = datetime.now(timezone.utc)
        await db.commit()
        if task.storyboard_id:
            await _sync_storyboard(db, task.storyboard_id)


async def _sync_storyboard(db, storyboard_id: str) -> None:
    """镜头任务结束后同步分镜状态；全部成功则拼接成片"""
    from sqlalchemy.orm import selectinload

    sb = await db.scalar(
        select(Storyboard)
        .options(selectinload(Storyboard.shots))
        .where(Storyboard.id == storyboard_id)
    )
    if sb is None:
        return
    shots = sb.shots
    if not shots:
        return
    statuses = {s.status for s in shots}
    if "pending" in statuses or "running" in statuses:
        sb.status = "generating"
        await db.commit()
        return
    if "failed" in statuses:
        sb.status = "partial"
        sb.error = "部分镜头失败，可重试失败镜头"
        await db.commit()
        return

    # 全部成功 → 拼接
    try:
        videos = [Path(s.video_path) for s in shots if s.video_path]
        final = await asyncio.to_thread(
            video_utils.concat_videos, videos, VIDEOS_DIR / f"storyboard_{sb.id}.mp4"
        )
        sb.final_video_path = str(final)
        sb.status = "done"
        sb.error = None
    except Exception as e:  # noqa: BLE001
        sb.status = "partial"
        sb.error = f"拼接失败: {e}"
    await db.commit()


def _snapshot(task: Task) -> dict:
    return {
        "provider": task.provider,
        "prompt": task.prompt,
        "optimized_prompt": task.optimized_prompt,
        "image_path": task.image_path,
        "duration": task.duration,
        "aspect_ratio": task.aspect_ratio,
        "seed": task.seed,
    }
