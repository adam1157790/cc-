"""智谱开放平台（CogVideoX-3）适配器。

文档：https://docs.bigmodel.cn/cn/guide/models/cogvideox/cogvideox-3
流程：POST /api/paas/v4/videos/generations 提交 → GET /api/paas/v4/async-result/{id} 查询。
i2v 时把图片 base64 内嵌在 prompt 末尾（智谱的约定："{text} --img {b64}"）。
"""
import base64
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from .base import PollResult, ProviderError, SubmitResult, VideoProvider

BASE = "https://open.bigmodel.cn/api/paas/v4"


class ZhipuProvider(VideoProvider):
    name = "zhipu"
    supports_i2v = True
    supported_durations = (5, 10)
    supported_ratios = ("16:9", "9:16")

    def _headers(self) -> dict:
        if not settings.zhipu_api_key:
            raise ProviderError("未配置 ZHIPU_API_KEY")
        return {"Authorization": f"Bearer {settings.zhipu_api_key}"}

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
        image_path: Optional[str] = None,
    ) -> SubmitResult:
        model = settings.zhipu_i2v_model if image_path else settings.zhipu_t2v_model
        full_prompt = prompt
        if image_path:
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            full_prompt = f"{prompt} --img {b64}"

        payload: dict = {
            "model": model,
            "prompt": full_prompt,
            "size": "1920x1080" if aspect_ratio == "16:9" else "1080x1920",
            "duration": duration,  # 智谱仅支持 5 / 10
        }
        if seed is not None:
            payload["seed"] = seed

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BASE}/videos/generations", headers=self._headers(), json=payload)
            data = self._check(resp)
            task_id = data.get("id")
            if not task_id:
                raise ProviderError(f"智谱未返回任务ID: {data}")
            return SubmitResult(provider_task_id=task_id)

    async def poll(self, provider_task_id: str) -> PollResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE}/async-result/{provider_task_id}", headers=self._headers()
            )
            data = self._check(resp)
        status = data.get("task_status")
        if status == "SUCCESS":
            url = data.get("video_result", [{}])[0].get("url")
            if not url:
                raise ProviderError(f"成功但未找到视频URL: {data}")
            return PollResult("succeeded", 100, video_url=url)
        if status in ("FAIL", "FAILED"):
            return PollResult("failed", 100, error=str(data.get("error", "")) or "智谱生成失败")
        # PROCESSING / VALIDATING
        return PollResult("running", 50)

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise ProviderError(f"智谱HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

