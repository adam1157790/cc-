"""数据库模型：用户 / 生成任务 / 分镜"""
import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_quota: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    images: Mapped[list["ImageTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")


async def quota_used_today(db, user_id: int) -> int:
    """今天已提交的任务数（配额扣减口径）。必须在会话内调用。"""
    start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    from sqlalchemy import func, select

    n = await db.scalar(
        select(func.count(Task.id)).where(Task.user_id == user_id, Task.created_at >= start)
    )
    return n or 0


class Task(Base):
    """一次视频生成任务（文生视频 / 图生视频 / 分镜中的单镜头）"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    storyboard_id: Mapped[Optional[str]] = mapped_column(ForeignKey("storyboards.id"), nullable=True, index=True)
    shot_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 分镜内镜头序号

    task_type: Mapped[str] = mapped_column(String(16))  # t2v | i2v
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    optimized_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # 图生视频首帧

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending -> running -> succeeded | failed | canceled
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    provider_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    duration: Mapped[int] = mapped_column(Integer, default=5)  # 期望秒数
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="16:9")
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="tasks")
    storyboard: Mapped[Optional["Storyboard"]] = relationship(back_populates="shots")


class ImageTask(Base):
    """一次文生图任务（与视频 Task 完全独立，不占视频配额、不进视频队列）

    task_type: t2i（纯文生图）| e2i（参考图编辑，可选功能）
    """

    __tablename__ = "image_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    task_type: Mapped[str] = mapped_column(String(8), default="t2i")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt: Mapped[str] = mapped_column(Text)
    optimized_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ref_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # e2i 参考图

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending -> running -> succeeded | failed | canceled
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    provider_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    size: Mapped[str] = mapped_column(String(32), default="2048x2048")
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    guidance: Mapped[int] = mapped_column(Integer, default=0)  # 提示词遵循度 0-100（厂商参数映射在 provider 内做）

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="images")


async def image_quota_used_today(db, user_id: int) -> int:
    """今天已提交的文生图任务数（独立于视频配额口径）"""
    start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    from sqlalchemy import func, select

    n = await db.scalar(
        select(func.count(ImageTask.id)).where(ImageTask.user_id == user_id, ImageTask.created_at >= start)
    )
    return n or 0


class Storyboard(Base):
    """分镜脚本：多个镜头 → 逐镜头生成 → ffmpeg 拼接成成片"""

    __tablename__ = "storyboards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名分镜")
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    # draft | generating | done | partial（部分镜头失败）
    final_video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    shots: Mapped[list["Task"]] = relationship(
        back_populates="storyboard", cascade="all, delete-orphan", order_by="Task.shot_index"
    )
