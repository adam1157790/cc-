"""文生图提示词智能优化：把口语描述扩写为结构化图像提示词。

与视频版 prompt_optimizer 并行存在、互不影响。「精确输出」的关键：
LLM 按主体/构图/光线/风格/色彩结构化扩写 + 负面词，并允许用户传入
必须出现的精确元素清单（文字、数量、颜色、位置），扩写时严格保留。
"""
import json

import httpx

from ..config import settings

IMAGE_SYSTEM_PROMPT = """你是一名专业的AI文生图提示词工程师。用户给你一段画面描述，你要把它扩写为
高质量的文生图提示词，严格按以下JSON格式输出，不要输出任何其他内容：
{
  "optimized_prompt": "扩写后的提示词（中文，60-150字，按顺序包含：主体及其精确外观细节、
    数量与位置关系、动作/姿态、构图与景别、光线方向与氛围、艺术风格、色彩基调、材质与质感）",
  "negative_prompt": "需要避免的元素（英文，逗号分隔，如: blurry, watermark, text, extra fingers, distorted hands）"
}
扩写原则：
1. 忠于用户原意，绝不添加用户没提到的新主体，只做细节丰富
2. 用户的精确要求（数量、文字内容、颜色、位置）必须一字不差地保留，不得改写
3. 静态画面：描述一个瞬间，不要出现时间流逝或多帧叙事
4. 构图要具体（三分法/中心构图/视线引导），这是文生图精确度的核心
5. 如用户描述了画面中要出现的文字，将其放在引号中并说明其位置与字体风格"""


async def optimize_image_prompt(user_prompt: str) -> dict:
    """返回 {optimized_prompt, negative_prompt}"""
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法使用提示词优化")

    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers=headers, json=body
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM服务错误 {resp.status_code}: {resp.text[:300]}")
        content = resp.json()["choices"][0]["message"]["content"]

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"LLM返回无法解析: {content[:200]}")
    data = json.loads(text[start : end + 1])
    return {
        "optimized_prompt": data.get("optimized_prompt", ""),
        "negative_prompt": data.get("negative_prompt", ""),
    }
