"""任务路由：创建生成任务（含多候选）/ 列表 / 详情 / 取消 / 删除 / 视频文件"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import Task, User, quota_used_today
from ..providers import available_providers, ProviderError
from ..services import worker
from ..services.prompt_optimizer import optimize_prompt, split_prompt_into_shots
from .deps import get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
UPLOAD_DIR = worker.VIDEOS_DIR.parent / "uploads"


class CreateTaskIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    provider: str
    task_type: str = "t2v"  # t2v | i2v
    duration: int = 5
    aspect_ratio: str = "16:9"
    seed: int | None = None
    optimize: bool = True
    candidates: int = 1  # 多候选并行生成数
    image_id: str | None = None  # 上传图片返回的ID
    total_duration: int | None = None  # 长视频模式：总时长>10时自动分镜拼接


class OptimizeIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


@router.get("/providers")
async def list_providers(user: User = Depends(get_current_user)):
    return available_providers()


@router.post("/optimize")
async def optimize(body: OptimizeIn, user: User = Depends(get_current_user)):
    """提示词智能优化（前端创建任务前预览效果）"""
    try:
        return await optimize_prompt(body.prompt)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/upload-image")
async def upload_image(file: UploadFile, user: User = Depends(get_current_user)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"仅支持 JPEG/PNG/WebP，收到 {file.content_type}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_id = uuid.uuid4().hex[:16]
    dest = UPLOAD_DIR / f"{image_id}{Path(file.filename or 'img.jpg').suffix or '.jpg'}"
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过15MB")
    dest.write_bytes(data)
    return {"image_id": str(dest)}


@router.post("")
async def create_task(body: CreateTaskIn, user: User = Depends(get_current_user)):
    # 长视频模式：total_duration>10 时走自动分镜流程
    if body.total_duration and body.total_duration > 10:
        return await _create_long_video(body, user)

    # 配额：candidates 数计入配额（QUOTA_ENABLED=false 时不限制）
    if settings.quota_enabled:
        async with SessionLocal() as db:
            used = await quota_used_today(db, user.id)
        if used + body.candidates > user.daily_quota:
            raise HTTPException(
                429, f"今日配额不足（已用{used}/{user.daily_quota}）"
            )
    if body.task_type not in ("t2v", "i2v"):
        raise HTTPException(400, "task_type 只能是 t2v 或 i2v")
    if body.candidates < 1 or body.candidates > 4:
        raise HTTPException(400, "candidates 取值 1-4")

    providers = {p["name"] for p in available_providers()}
    if body.provider not in providers:
        raise HTTPException(400, f"引擎不可用: {body.provider}")

    image_path = None
    if body.task_type == "i2v":
        if not body.image_id:
            raise HTTPException(400, "图生视频必须上传参考图")
        image_path = str(UPLOAD_DIR / Path(body.image_id).name)
        if not Path(image_path).exists():
            raise HTTPException(400, "参考图不存在，请重新上传")

    # 提示词优化（一次性，所有候选共用）
    optimized = None
    if body.optimize:
        try:
            result = await optimize_prompt(body.prompt)
            optimized = result["optimized_prompt"]
        except RuntimeError:
            optimized = None  # LLM不可用时降级为原始提示词

    from ..providers import get_provider

    provider = get_provider(body.provider)
    if body.task_type == "i2v" and not provider.supports_i2v:
        raise HTTPException(400, f"{body.provider} 不支持图生视频")

    created = []
    async with SessionLocal() as db:
        db_user = await db.get(User, user.id)
        for i in range(body.candidates):
            task = Task(
                id=worker.new_task_id(),
                user_id=user.id,
                task_type=body.task_type,
                provider=body.provider,
                model="",
                prompt=body.prompt,
                optimized_prompt=optimized,
                image_path=image_path,
                duration=body.duration,
                aspect_ratio=body.aspect_ratio,
                seed=body.seed + i if body.seed is not None else None,
                status="pending",
            )
            db.add(task)
            created.append(task.id)
        await db.commit()

    for tid in created:
        await worker.enqueue(tid)

    return {"task_ids": created}


@router.get("")
async def list_tasks(
    user: User = Depends(get_current_user),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    async with SessionLocal() as db:
        q = select(Task).where(Task.user_id == user.id, Task.storyboard_id.is_(None))
        if status:
            q = q.where(Task.status == status)
        q = q.order_by(Task.created_at.desc()).limit(min(limit, 200)).offset(offset)
        tasks = (await db.scalars(q)).all()
    return [_task_out(t) for t in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str, user: User = Depends(get_current_user)):
    task = await _own_task(task_id, user)
    return _task_out(task, detail=True)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, user: User = Depends(get_current_user)):
    task = await _own_task(task_id, user)
    if task.status not in ("pending", "running"):
        raise HTTPException(400, f"任务已是终态 {task.status}")
    async with SessionLocal() as db:
        t = await db.get(Task, task_id)
        t.status = "canceled"
        t.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await db.commit()
    return {"ok": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    task = await _own_task(task_id, user)
    if task.status in ("pending", "running"):
        raise HTTPException(400, "请先取消任务再删除")
    async with SessionLocal() as db:
        t = await db.get(Task, task_id)
        await db.delete(t)
        await db.commit()
    # 清理本地文件
    for p in (task.video_path, task.cover_path):
        if p:
            Path(p).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{task_id}/video")
async def get_video(task_id: str, user: User = Depends(get_current_user)):
    task = await _own_task(task_id, user)
    if not task.video_path or not Path(task.video_path).exists():
        raise HTTPException(404, "视频尚未生成完成")
    return FileResponse(task.video_path, media_type="video/mp4", filename=f"{task_id}.mp4")


@router.get("/{task_id}/cover")
async def get_cover(task_id: str, user: User = Depends(get_current_user)):
    task = await _own_task(task_id, user)
    if not task.cover_path or not Path(task.cover_path).exists():
        raise HTTPException(404, "无封面")
    return FileResponse(task.cover_path, media_type="image/jpeg")


async def _own_task(task_id: str, user: User) -> Task:
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    return task


def _task_out(t: Task, detail: bool = False) -> dict:
    out = {
        "id": t.id,
        "status": t.status,
        "progress": t.progress,
        "task_type": t.task_type,
        "provider": t.provider,
        "prompt": t.prompt,
        "optimized_prompt": t.optimized_prompt,
        "duration": t.duration,
        "aspect_ratio": t.aspect_ratio,
        "has_video": bool(t.video_path),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "error": t.error,
    }
    if detail:
        out["seed"] = t.seed
        out["finished_at"] = t.finished_at.isoformat() if t.finished_at else None
    return out


async def _create_long_video(body: CreateTaskIn, user: User):
    """长视频模式：LLM 把单条描述拆成多个连贯镜头 → 并行生成 → 自动拼接。

    复用分镜(storyboard)机制：每镜头 10 秒，镜头数 = ceil(total_duration/10)，
    允许最后一个镜头用 5 秒补齐到用户要的总时长（如 25 秒 = 10+10+5）。
    """
    if body.total_duration is None or body.total_duration > 200:
        raise HTTPException(400, "总时长需在 11-200 秒之间")
    full_shots = body.total_duration // 10
    remainder = body.total_duration % 10
    if remainder and remainder < 5:
        # 不足5秒的零头并入上一镜头（如 22 秒 = 10+10，不足部分忽略并提示）
        remainder = 0
        if full_shots == 0:
            raise HTTPException(400, "总时长至少 15 秒（或选 10 秒以内）")
    shot_count = full_shots + (1 if remainder else 0)

    # 配额：镜头数计入配额（QUOTA_ENABLED=false 时不限制）
    if settings.quota_enabled:
        async with SessionLocal() as db:
            used = await quota_used_today(db, user.id)
            if used + shot_count > user.daily_quota:
                raise HTTPException(
                    429, f"今日配额不足：长视频需{shot_count}次生成，已用{used}/{user.daily_quota}"
                )

    providers = {p["name"] for p in available_providers()}
    if body.provider not in providers:
        raise HTTPException(400, f"引擎不可用: {body.provider}")

    # LLM 拆分镜头；失败则用原描述平铺（每个镜头同样内容）
    try:
        shot_prompts = await split_prompt_into_shots(body.prompt, shot_count)
    except RuntimeError as e:
        raise HTTPException(400, f"自动分镜失败: {e}")

    # 组装每个镜头的时长与提示词
    durations = [10] * full_shots + ([remainder or 10] if remainder else [])
    # 每个镜头提示词再走一次优化（结构化扩写，提高单镜头质量）
    final_prompts = []
    for p in shot_prompts:
        if body.optimize:
            try:
                final_prompts.append((await optimize_prompt(p))["optimized_prompt"])
            except RuntimeError:
                final_prompts.append(p)
        else:
            final_prompts.append(p)

    from ..models import Storyboard

    sb_id = worker.new_task_id()
    shot_ids = []
    async with SessionLocal() as db:
        sb = Storyboard(id=sb_id, user_id=user.id, title=body.prompt[:20] or "长视频")
        sb.config = {"provider": body.provider, "aspect_ratio": body.aspect_ratio}
        sb.status = "generating"
        db.add(sb)
        for i, (p, d) in enumerate(zip(shot_prompts, durations)):
            t = Task(
                id=worker.new_task_id(),
                user_id=user.id,
                storyboard_id=sb_id,
                shot_index=i,
                task_type="t2v",
                provider=body.provider,
                model="",
                prompt=p,
                optimized_prompt=final_prompts[i],
                duration=d,
                aspect_ratio=body.aspect_ratio,
                status="pending",
            )
            db.add(t)
            shot_ids.append(t.id)
        await db.commit()

    for tid in shot_ids:
        await worker.enqueue(tid)
    return {
        "storyboard_id": sb_id,
        "shot_task_ids": shot_ids,
        "shot_count": shot_count,
        "total_duration": sum(durations),
        "message": f"已自动拆分为{shot_count}个镜头并行生成，全部完成后自动拼接为{sum(durations)}秒长视频，请到「分镜脚本」页查看进度",
    }
