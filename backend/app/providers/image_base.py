"""可插拔文生图引擎抽象层（与视频 providers 完全平行，互不影响）。

图像接口大多是同步返回图片（base64 或 URL），所以 submit 可直接带回结果；
个别异步接口在 poll 中轮询。新增厂商只需在本文件 available_image_providers
注册，不改业务代码。
"""
import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageSubmitResult:
    provider_task_id: Optional[str] = None
    # 同步接口直接返回图片（base64 data URI 或 http URL），无需轮询
    image_url: Optional[str] = None


@dataclass
class ImagePollResult:
    status: str  # running | succeeded | failed
    image_url: Optional[str] = None
    error: Optional[str] = None


class ImageProvider(abc.ABC):
    name: str = "base"
    supports_e2i: bool = False  # 是否支持参考图编辑（e2i）
    supported_sizes: tuple = ("1024x1024",)

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        size: str = "2048x2048",
        seed: Optional[int] = None,
        guidance: int = 0,  # 0-100 提示词遵循度
        ref_image_path: Optional[str] = None,
    ) -> ImageSubmitResult:
        """生成图片；同步接口直接返回图片地址/数据，异步接口返回任务ID"""

    async def poll(self, provider_task_id: str) -> ImagePollResult:
        raise NotImplementedError(f"{self.name} 为同步接口，无需轮询")


def available_image_providers() -> list[dict]:
    """列出已配置 API Key 的文生图引擎，供前端选择"""
    from ..config import settings

    out = []
    if settings.volcengine_api_key:
        from .volcengine_image import VolcengineImageProvider

        out.append({
            "name": "volcengine",
            "label": "火山引擎 Seedream 4.0",
            "supports_e2i": VolcengineImageProvider.supports_e2i,
        })
    if settings.zhipu_api_key:
        from .zhipu_image import ZhipuImageProvider

        out.append({
            "name": "zhipu",
            "label": "智谱 CogView-4",
            "supports_e2i": ZhipuImageProvider.supports_e2i,
        })
    if os_environ_flag("ENABLE_MOCK_PROVIDER"):
        from .mock_image import MockImageProvider

        out.append({"name": "mock", "label": "测试图像引擎", "supports_e2i": True})
    return out


def os_environ_flag(name: str) -> bool:
    import os

    return os.environ.get(name) == "1"


def get_image_provider(name: str) -> ImageProvider:
    from ..config import settings

    if name == "volcengine" and settings.volcengine_api_key:
        from .volcengine_image import VolcengineImageProvider

        return VolcengineImageProvider()
    if name == "zhipu" and settings.zhipu_api_key:
        from .zhipu_image import ZhipuImageProvider

        return ZhipuImageProvider()
    if name == "mock" and os_environ_flag("ENABLE_MOCK_PROVIDER"):
        from .mock_image import MockImageProvider

        return MockImageProvider()
    raise ValueError(f"文生图引擎不可用: {name}")
