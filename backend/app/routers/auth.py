"""认证路由：注册 / 登录 / 当前用户信息"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..config import settings
from ..database import SessionLocal
from ..models import User, quota_used_today
from ..security import create_token, hash_password, verify_password
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(RegisterIn):
    pass


class ResetPasswordIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/register")
async def register(body: RegisterIn):
    if not settings.allow_registration:
        raise HTTPException(403, "当前已关闭注册")
    async with SessionLocal() as db:
        exists = await db.scalar(select(User).where(User.username == body.username))
        if exists:
            raise HTTPException(400, "用户名已存在")
        count = await db.scalar(select(func.count(User.id)))
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            is_admin=(count == 0),  # 第一个注册的用户自动成为管理员
            daily_quota=settings.default_daily_quota,
        )
        db.add(user)
        await db.commit()
        token = create_token(user.id, user.is_admin)
    return {"token": token, "username": user.username, "is_admin": user.is_admin}


@router.post("/login")
async def login(body: LoginIn):
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "用户名或密码错误")
    token = create_token(user.id, user.is_admin)
    return {"token": token, "username": user.username, "is_admin": user.is_admin}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordIn):
    """自助修改密码：验证旧密码后设置新密码（无需登录态，登录页可用）"""
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == body.username))
        if user is None or not verify_password(body.old_password, user.password_hash):
            raise HTTPException(400, "用户名或旧密码错误")
        user.password_hash = hash_password(body.new_password)
        await db.commit()
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    async with SessionLocal() as db:
        used = await quota_used_today(db, user.id)
    return {
        "username": user.username,
        "is_admin": user.is_admin,
        "daily_quota": user.daily_quota,
        "quota_used_today": used,
        "quota_enabled": settings.quota_enabled,
    }
