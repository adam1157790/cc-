"""智谱开放平台 CogView-4 文生图适配器。

文档：https://docs.bigmodel.cn/cn/guide/models/cogview/cogview-4
POST /api/paas/v4/images/generations → data[0].url（同步返回）
CogView-4 的 size 只支持枚举档位，guidance 不支持（保留参数以统一接口）。
"""
from typing import Optional

import httpx

from ..config import settings
from .image_base import ImageProvider, ImageSubmitResult

BASE = "https://open.bigmodel.cn/api/paas/v4"
SUPPORTED_SIZES = ("1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440")


class ZhipuImageProvider(ImageProvider):
    name = "zhipu"
    supports_e2i = False

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.zhipu_api_key}"}

    async def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        seed: Optional[int] = None,
        guidance: int = 0,
        ref_image_path: Optional[str] = None,
    ) -> ImageSubmitResult:
        if ref_image_path:
            raise RuntimeError("智谱 CogView 不支持参考图编辑，请换用火山引擎")
        payload: dict = {
            "model": settings.zhipu_image_model,
            "prompt": prompt,
            "size": size if size in SUPPORTED_SIZES else "1024x1024",
        }
        if seed is not None:
            payload["seed"] = seed
        # guidance：CogView 不支持该参数，忽略（接口签名统一）

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{BASE}/images/generations", headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"智谱HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()

        items = data.get("data") or []
        if not items or not items[0].get("url"):
            raise RuntimeError(f"智谱未返回图片: {str(data)[:300]}")
        return ImageSubmitResult(image_url=items[0]["url"])

    @staticmethod
    def normalize_size(size: str) -> str:
        mapping = {
            "1:1": "1024x1024", "16:9": "1440x720", "9:16": "720x1440",
            "4:3": "1152x864", "3:4": "864x1152", "3:2": "1152x864", "2:3": "864x1152",
        }
        return mapping.get(size, size if size in SUPPORTED_SIZES else "1024x1024")
