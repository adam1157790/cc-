"""分镜路由：创建多镜头脚本 → 并行生成 → 自动拼接成片"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import SessionLocal
from ..models import Storyboard, Task, User, quota_used_today
from ..providers import available_providers, get_provider
from ..services import worker
from ..services.prompt_optimizer import optimize_prompt
from .deps import get_current_user

router = APIRouter(prefix="/api/storyboards", tags=["storyboards"])


class ShotIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    duration: int = 5
    optimize: bool = True


class CreateStoryboardIn(BaseModel):
    title: str = "未命名分镜"
    provider: str
    aspect_ratio: str = "16:9"
    shots: list[ShotIn] = Field(min_length=1, max_length=20)


@router.post("")
async def create_storyboard(body: CreateStoryboardIn, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        used = await quota_used_today(db, user.id)
    if used + len(body.shots) > user.daily_quota:
        raise HTTPException(
            429, f"今日配额不足：本分镜需{len(body.shots)}次生成，已用{used}/{user.daily_quota}"
        )
    providers = {p["name"] for p in available_providers()}
    if body.provider not in providers:
        raise HTTPException(400, f"引擎不可用: {body.provider}")

    sb_id = worker.new_task_id()
    shot_ids = []
    async with SessionLocal() as db:
        sb = Storyboard(id=sb_id, user_id=user.id, title=body.title)
        sb.config = {"provider": body.provider, "aspect_ratio": body.aspect_ratio}
        db.add(sb)
        for i, shot in enumerate(body.shots):
            optimized = None
            if shot.optimize:
                try:
                    optimized = (await optimize_prompt(shot.prompt))["optimized_prompt"]
                except RuntimeError:
                    optimized = None
            t = Task(
                id=worker.new_task_id(),
                user_id=user.id,
                storyboard_id=sb.id,
                shot_index=i,
                task_type="t2v",
                provider=body.provider,
                model="",
                prompt=shot.prompt,
                optimized_prompt=optimized,
                duration=shot.duration,
                aspect_ratio=body.aspect_ratio,
                status="pending",
            )
            db.add(t)
            shot_ids.append(t.id)
        sb.status = "generating"
        await db.commit()

    for tid in shot_ids:
        await worker.enqueue(tid)
    return {"storyboard_id": sb_id, "shot_task_ids": shot_ids}


@router.get("")
async def list_storyboards(user: User = Depends(get_current_user), all_users: bool = False):
    """管理员可传 all_users=true 查看全部分镜（带 owner 用户名）"""
    async with SessionLocal() as db:
        stmt = (
            select(Storyboard, User.username)
            .join(User)
            .options(selectinload(Storyboard.shots))
            .order_by(Storyboard.created_at.desc())
        )
        if not (all_users and user.is_admin):
            stmt = stmt.where(Storyboard.user_id == user.id)
        rows = (await db.execute(stmt)).all()
    result = []
    for sb, owner_name in rows:
        out = _sb_out(sb)
        out["owner"] = owner_name
        result.append(out)
    return result


@router.get("/{sb_id}")
async def get_storyboard(sb_id: str, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(Storyboard, User.username)
                .join(User)
                .options(selectinload(Storyboard.shots))
                .where(Storyboard.id == sb_id)
            )
        ).first()
        sb, owner_name = row if row else (None, None)
        if sb is None or (sb.user_id != user.id and not user.is_admin):
            raise HTTPException(404, "分镜不存在")
        shots = sb.shots
    out = _sb_out(sb, shots=shots, detail=True)
    out["owner"] = owner_name
    return out


@router.post("/{sb_id}/shots/{shot_index}/retry")
async def retry_shot(sb_id: str, shot_index: int, user: User = Depends(get_current_user)):
    """重试失败的镜头"""
    async with SessionLocal() as db:
        sb = await db.scalar(
            select(Storyboard)
            .options(selectinload(Storyboard.shots))
            .where(Storyboard.id == sb_id)
        )
        if sb is None or sb.user_id != user.id:
            raise HTTPException(404, "分镜不存在")
        shot = next((s for s in sb.shots if s.shot_index == shot_index), None)
        if shot is None:
            raise HTTPException(404, "镜头不存在")
        if shot.status not in ("failed",):
            raise HTTPException(400, "只能重试失败的镜头")
        shot.status = "pending"
        shot.progress = 0
        shot.error = None
        sb.status = "generating"
        await db.commit()
        shot_id = shot.id
    await worker.enqueue(shot_id)
    return {"ok": True, "task_id": shot_id}


@router.delete("/{sb_id}")
async def delete_storyboard(sb_id: str, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        sb = await db.scalar(
            select(Storyboard)
            .options(selectinload(Storyboard.shots))
            .where(Storyboard.id == sb_id)
        )
        if sb is None or sb.user_id != user.id:
            raise HTTPException(404, "分镜不存在")
        if any(s.status in ("pending", "running") for s in sb.shots):
            raise HTTPException(400, "请先等待或取消生成中的镜头")
        paths = [s.video_path for s in sb.shots if s.video_path] + (
            [sb.final_video_path] if sb.final_video_path else []
        )
        await db.delete(sb)
        await db.commit()
    for p in paths:
        Path(p).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{sb_id}/final-video")
async def get_final_video(sb_id: str, user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        sb = await db.scalar(select(Storyboard).where(Storyboard.id == sb_id))
        if sb is None or (sb.user_id != user.id and not user.is_admin):
            raise HTTPException(404, "分镜不存在")
    if not sb.final_video_path or not Path(sb.final_video_path).exists():
        raise HTTPException(404, "成片尚未生成")
    return FileResponse(sb.final_video_path, media_type="video/mp4", filename=f"{sb.title}.mp4")


def _sb_out(sb: Storyboard, shots=None, detail: bool = False) -> dict:
    out = {
        "id": sb.id,
        "title": sb.title,
        "status": sb.status,
        "shot_count": len(sb.shots) if shots is None else len(shots),
        "has_final_video": bool(sb.final_video_path),
        "error": sb.error,
        "created_at": sb.created_at.isoformat() if sb.created_at else None,
    }
    if detail and shots is not None:
        out["shots"] = [
            {
                "task_id": s.id,
                "shot_index": s.shot_index,
                "prompt": s.prompt,
                "optimized_prompt": s.optimized_prompt,
                "status": s.status,
                "progress": s.progress,
                "duration": s.duration,
                "has_video": bool(s.video_path),
                "error": s.error,
            }
            for s in shots
        ]
    return out
