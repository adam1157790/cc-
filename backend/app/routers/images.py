"""文生图路由：引擎列表 / 提示词优化 / 创建任务（含多候选）/ 列表 / 图片文件 / 删除。

与 /api/tasks 完全独立：独立配额（IMAGE_DAILY_QUOTA）、独立数据表。
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import ImageTask, User, image_quota_used_today
from ..providers.image_base import available_image_providers, get_image_provider
from ..services import image_worker
from ..services.image_prompt_optimizer import optimize_image_prompt
from .deps import get_current_user

router = APIRouter(prefix="/api/images", tags=["images"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
UPLOAD_DIR = image_worker.IMAGES_DIR.parent / "uploads"


class CreateImageIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    provider: str
    size: str = "1:1"  # 通用比例（1:1/16:9/9:16/4:3/3:4）或像素 WxH
    seed: int | None = None  # 固定 seed + 固定提示词 = 可精确复现
    guidance: int = 0  # 0-100 提示词遵循度（0=引擎默认）
    optimize: bool = True
    candidates: int = 1  # 多候选并行（1-4）
    ref_image_id: str | None = None  # 参考图编辑模式（e2i，引擎支持时可用）


class OptimizeImageIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


@router.get("/providers")
async def list_image_providers(user: User = Depends(get_current_user)):
    return available_image_providers()


@router.get("/quota")
async def image_quota(user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        used = await image_quota_used_today(db, user.id)
    # quota_enabled=false 时前端显示「无限制」
    return {"used": used, "quota": settings.image_daily_quota, "unlimited": not settings.quota_enabled}


@router.post("/optimize")
async def optimize(body: OptimizeImageIn, user: User = Depends(get_current_user)):
    """文生图提示词优化（创建前预览；与视频版提示词优化相互独立）"""
    try:
        return await optimize_image_prompt(body.prompt)
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
async def create_image(body: CreateImageIn, user: User = Depends(get_current_user)):
    if body.candidates < 1 or body.candidates > 4:
        raise HTTPException(400, "candidates 取值 1-4")
    if not 0 <= body.guidance <= 100:
        raise HTTPException(400, "guidance 取值 0-100")

    providers = {p["name"] for p in available_image_providers()}
    if body.provider not in providers:
        raise HTTPException(400, f"文生图引擎不可用: {body.provider}")

    # 独立配额检查（不占视频配额；QUOTA_ENABLED=false 时不限制）
    if settings.quota_enabled:
        async with SessionLocal() as db:
            used = await image_quota_used_today(db, user.id)
        if used + body.candidates > settings.image_daily_quota:
            raise HTTPException(429, f"今日文生图配额不足（已用{used}/{settings.image_daily_quota}）")

    provider = get_image_provider(body.provider)

    # 尺寸归一化到引擎支持的像素值
    if hasattr(provider, "normalize_size"):
        size = provider.normalize_size(body.size)
    else:
        size = body.size

    ref_image_path = None
    if body.ref_image_id:
        if not provider.supports_e2i:
            raise HTTPException(400, f"{body.provider} 不支持参考图编辑")
        ref_image_path = str(UPLOAD_DIR / Path(body.ref_image_id).name)
        if not Path(ref_image_path).exists():
            raise HTTPException(400, "参考图不存在，请重新上传")

    # 提示词优化（一次，所有候选共用）
    optimized = None
    if body.optimize:
        try:
            optimized = (await optimize_image_prompt(body.prompt))["optimized_prompt"]
        except RuntimeError:
            optimized = None  # LLM 不可用时降级为原始提示词

    created = []
    async with SessionLocal() as db:
        for i in range(body.candidates):
            task = ImageTask(
                id=image_worker.new_image_task_id(),
                user_id=user.id,
                task_type="e2i" if ref_image_path else "t2i",
                provider=body.provider,
                model="",
                prompt=body.prompt,
                optimized_prompt=optimized,
                ref_image_path=ref_image_path,
                size=size,
                seed=body.seed + i if body.seed is not None else None,
                guidance=body.guidance,
                status="pending",
            )
            db.add(task)
            created.append(task.id)
        await db.commit()

    for tid in created:
        await image_worker.enqueue_image(tid)
    return {"task_ids": created}


@router.get("")
async def list_images(
    user: User = Depends(get_current_user),
    status: str | None = None,
    limit: int = 60,
    offset: int = 0,
):
    async with SessionLocal() as db:
        q = select(ImageTask).where(ImageTask.user_id == user.id)
        if status:
            q = q.where(ImageTask.status == status)
        q = q.order_by(ImageTask.created_at.desc()).limit(min(limit, 200)).offset(offset)
        tasks = (await db.scalars(q)).all()
    return [_out(t) for t in tasks]


@router.delete("/{task_id}")
async def delete_image(task_id: str, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        task = await db.get(ImageTask, task_id)
        if task is None or task.user_id != user.id:
            raise HTTPException(404, "任务不存在")
        if task.status in ("pending", "running"):
            raise HTTPException(400, "任务进行中，请稍后删除")
        await db.delete(task)
        await db.commit()
    if task.image_path:
        Path(task.image_path).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{task_id}/file")
async def get_image_file(task_id: str, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        task = await db.get(ImageTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    if not task.image_path or not Path(task.image_path).exists():
        raise HTTPException(404, "图片尚未生成完成")
    return FileResponse(task.image_path, media_type="image/png", filename=f"{task_id}.png")


def _out(t: ImageTask) -> dict:
    return {
        "id": t.id,
        "status": t.status,
        "progress": t.progress,
        "task_type": t.task_type,
        "provider": t.provider,
        "prompt": t.prompt,
        "optimized_prompt": t.optimized_prompt,
        "size": t.size,
        "seed": t.seed,
        "guidance": t.guidance,
        "has_image": bool(t.image_path),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "error": t.error,
    }
