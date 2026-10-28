"""管理后台路由：用户管理 / 全局任务统计 / 注册开关"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..config import settings
from ..database import SessionLocal
from ..models import Task, User, quota_used_today
from .deps import get_admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def stats(admin: User = Depends(get_admin_user)):
    async with SessionLocal() as db:
        user_count = await db.scalar(select(func.count(User.id)))
        task_count = await db.scalar(select(func.count(Task.id)))
        by_status = dict(
            (await db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status))).all()
        )
        # 最近7天每日生成量
        daily = []
        for i in range(6, -1, -1):
            day = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=i)).date()
            start = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
            end = start + dt.timedelta(days=1)
            n = await db.scalar(
                select(func.count(Task.id)).where(Task.created_at >= start, Task.created_at < end)
            )
            daily.append({"date": day.isoformat(), "count": n})
    return {
        "user_count": user_count,
        "task_count": task_count,
        "by_status": by_status,
        "daily": daily,
    }


@router.get("/users")
async def list_users(admin: User = Depends(get_admin_user)):
    async with SessionLocal() as db:
        users = (await db.scalars(select(User).order_by(User.id))).all()
        used_map = {}
        for u in users:
            used_map[u.id] = await quota_used_today(db, u.id)
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "daily_quota": u.daily_quota,
            "quota_used_today": used_map[u.id],
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class UpdateUserIn(BaseModel):
    daily_quota: int | None = Field(default=None, ge=0, le=1000)
    is_admin: bool | None = None


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserIn, admin: User = Depends(get_admin_user)):
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "用户不存在")
        if body.daily_quota is not None:
            user.daily_quota = body.daily_quota
        if body.is_admin is not None:
            if user.id == admin.id and not body.is_admin:
                raise HTTPException(400, "不能取消自己的管理员权限")
            user.is_admin = body.is_admin
        await db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, admin: User = Depends(get_admin_user)):
    if user_id == admin.id:
        raise HTTPException(400, "不能删除自己")
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "用户不存在")
        await db.delete(user)
        await db.commit()
    return {"ok": True}


@router.get("/settings")
async def get_settings(admin: User = Depends(get_admin_user)):
    return {"allow_registration": settings.allow_registration}
