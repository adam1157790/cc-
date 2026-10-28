"""认证依赖：Authorization 头或 ?token= 查询参数（供 <video>/<img> 标签使用）"""
from fastapi import Depends, HTTPException, Request

from ..database import SessionLocal
from ..models import User
from ..security import decode_token


async def get_current_user(request: Request) -> User:
    token = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    elif "token" in request.query_params:
        # <video src>、<img src> 等标签无法自定义请求头，用查询参数传 token
        token = request.query_params["token"]
    if not token:
        raise HTTPException(401, "未登录")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(401, "登录已过期，请重新登录")
    async with SessionLocal() as db:
        user = await db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "用户不存在")
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user
