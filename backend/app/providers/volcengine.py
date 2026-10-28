"""火山引擎方舟（豆包 Seedance）适配器。

文档：https://www.volcengine.com/docs/82379/1520757
流程：POST /api/v3/contents/generations/tasks 提交 → GET 同地址查询。
返回 60 秒 ~ 5 分钟，返回的 URL 有效期仅 24 小时，所以必须下载落盘。
"""
import base64
import json
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from .base import PollResult, ProviderError, SubmitResult, VideoProvider

BASE = "https://ark.cn-beijing.volces.com/api/v3"


class VolcengineProvider(VideoProvider):
    name = "volcengine"
    supports_i2v = True
    supported_durations = (5, 10)
    supported_ratios = ("16:9", "9:16", "4:3", "1:1", "3:4", "21:9", "480p", "720p", "1080p")

    def _headers(self) -> dict:
        if not settings.volcengine_api_key:
            raise ProviderError("未配置 VOLCENGINE_API_KEY")
        return {"Authorization": f"Bearer {settings.volcengine_api_key}"}

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
        image_path: Optional[str] = None,
    ) -> SubmitResult:
        text = json.dumps({"text": prompt})
        payload: dict = {
            "model": settings.volcengine_i2v_model if image_path else settings.volcengine_t2v_model,
            "content": [text],
        }
        if image_path:
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            payload["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        # 分辨率/时长参数放在 model 参数里（Seedance 的约定）
        ratio = aspect_ratio if ":" in aspect_ratio else "16:9"
        payload["model"] += f"?resolution={ratio.replace(':', '')}&duration={duration}"
        if seed is not None:
            payload["seed"] = seed

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BASE}/contents/generations/tasks", headers=self._headers(), json=payload)
            data = self._check(resp)
            task_id = data.get("id")
            if not task_id:
                raise ProviderError(f"方舟未返回任务ID: {data}")
            return SubmitResult(provider_task_id=task_id)

    async def poll(self, provider_task_id: str) -> PollResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE}/contents/generations/tasks/{provider_task_id}", headers=self._headers())
            data = self._check(resp)
        status = data.get("status")
        if status == "succeeded":
            # content.fe_model_output.video_url
            try:
                url = data["content"]["video_url"]
            except (KeyError, TypeError):
                items = data.get("content", [])
                url = None
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("video_url"):
                            url = item["video_url"]
                            break
                if not url:
                    raise ProviderError(f"成功但未找到视频URL: {json.dumps(data, ensure_ascii=False)[:500]}")
            return PollResult("succeeded", 100, video_url=url)
        if status == "failed":
            err = data.get("error") or json.dumps(data, ensure_ascii=False)[:300]
            return PollResult("failed", 100, error=str(err))
        # queued/running → 粗略进度映射
        progress = 10 if status == "queued" else 50
        return PollResult("running", progress)

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise ProviderError(f"方舟HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
