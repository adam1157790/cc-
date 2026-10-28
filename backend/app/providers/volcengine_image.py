"""火山引擎方舟 Seedream 文生图适配器（同步接口，直接返回 base64 图片）。

文档：https://www.volcengine.com/docs/82379/1541523
POST /api/v3/images/generations → data[0].url / b64_json
Seedream 4.0 支持 size / seed / guidance（0-30，值越大越贴合提示词，映射 0-100）。
"""
import base64
import json
import re
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from .image_base import ImageProvider, ImageSubmitResult

BASE = "https://ark.cn-beijing.volces.com/api/v3"
# Seedream 4.0 官方支持的尺寸（1K：2048x2048；2K 常用横竖幅；4K 旗舰）
SUPPORTED_SIZES = (
    "1K", "2K", "4K",
    "2048x2048", "1664x2048", "2048x1664",
    "2048x1152", "1152x2048", "1280x1664", "1664x1280",
    "1456x2048", "2048x1456", "1152x1456", "1456x1152",
    "1280x720", "720x1280", "1024x1024", "512x512",
)


class VolcengineImageProvider(ImageProvider):
    name = "volcengine"
    supports_e2i = True  # Seedream 4.0 支持参考图（image 参数）

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.volcengine_api_key}"}

    async def generate(
        self,
        prompt: str,
        *,
        size: str = "2048x2048",
        seed: Optional[int] = None,
        guidance: int = 0,
        ref_image_path: Optional[str] = None,
    ) -> ImageSubmitResult:
        payload: dict = {
            "model": settings.volcengine_image_model,
            "prompt": prompt,
            "size": size if ":" not in size else "2048x2048",
            # guidance 前端口径 0-100（默认0=厂商默认），映射到方舟 1-30：
            # 0 -> 不传（用默认）；100 -> 30
            "guidance": round(1 + guidance / 100 * 29) if guidance > 0 else None,
            "response_format": "url",
            "watermark": False,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if seed is not None:
            payload["seed"] = seed
        if ref_image_path:
            b64 = base64.b64encode(Path(ref_image_path).read_bytes()).decode()
            payload["image"] = f"data:image/jpeg;base64,{b64}"

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{BASE}/images/generations", headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"方舟HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"方舟未返回图片: {json.dumps(data, ensure_ascii=False)[:300]}")
        item = items[0]
        if item.get("url"):
            return ImageSubmitResult(image_url=item["url"])
        if item.get("b64_json"):
            return ImageSubmitResult(image_url=f"data:image/png;base64,{item['b64_json']}")
        raise RuntimeError(f"方舟返回中无图片字段: {item}")

    @staticmethod
    def normalize_size(size: str) -> str:
        """把通用比例请求（如 16:9）映射到 Seedream 支持的像素尺寸"""
        mapping = {
            "16:9": "2048x1152", "9:16": "1152x2048", "1:1": "2048x2048",
            "4:3": "1664x1280", "3:4": "1280x1664", "3:2": "2048x1456", "2:3": "1456x2048",
        }
        return mapping.get(size, size if re.fullmatch(r"\d+x\d+", size) else "2048x2048")
