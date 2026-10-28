"""可插拔视频生成引擎抽象层。

每个 Provider 实现三个能力：
  - submit(text/image, params) -> (provider_task_id, 也可直接返回视频URL)
  - poll(provider_task_id) -> (status, video_url)
  - submit 并不落盘；由 worker 负责下载到本地。

新增一家厂商只需在 providers/__init__.py 注册，不改业务代码。
"""
import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class SubmitResult:
    provider_task_id: Optional[str]
    # 少数同步接口直接返回结果；此时无需轮询
    video_url: Optional[str] = None


@dataclass
class PollResult:
    status: str  # running | succeeded | failed
    progress: int  # 0-100
    video_url: Optional[str] = None
    error: Optional[str] = None


class VideoProvider(abc.ABC):
    name: str = "base"
    supports_i2v: bool = False
    supported_durations: tuple = (5,)
    supported_ratios: tuple = ("16:9",)

    @abc.abstractmethod
    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
        image_path: Optional[str] = None,
    ) -> SubmitResult:
        """提交生成请求，返回厂商侧任务ID或直接的视频URL"""

    @abc.abstractmethod
    async def poll(self, provider_task_id: str) -> PollResult:
        """查询任务状态；status 只能是 running/succeeded/failed"""


class ProviderError(Exception):
    """厂商接口报错（如参数不合法、内容审核不通过、余额不足）"""


def register_provider(name: str, cls: type[VideoProvider]) -> None:
    PROVIDERS[name] = cls


PROVIDERS: dict[str, type[VideoProvider]] = {}


def get_provider(name: str) -> VideoProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(f"未注册的生成引擎: {name}")
    return cls()


def available_providers() -> list[dict]:
    """列出已配置 API Key 的引擎，供前端选择"""
    from ..config import settings

    out = []
    if settings.volcengine_api_key:
        from .volcengine import VolcengineProvider

        out.append({
            "name": "volcengine",
            "label": "火山引擎 Seedance",
            "supports_i2v": VolcengineProvider.supports_i2v,
            "supports_first_frame": True,
        })
    if settings.zhipu_api_key:
        from .zhipu import ZhipuProvider

        out.append({
            "name": "zhipu",
            "label": "智谱 CogVideoX",
            "supports_i2v": ZhipuProvider.supports_i2v,
            "supports_first_frame": True,
        })
    if "mock" in PROVIDERS:
        out.append({"name": "mock", "label": "测试引擎", "supports_i2v": True, "supports_first_frame": True})
    return out
