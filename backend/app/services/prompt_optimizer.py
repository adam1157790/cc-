"""提示词智能优化：调用 OpenAI 兼容 LLM 把口语化描述扩写为专业视频提示词。

「精确度高」的关键之一：用户说"一只猫在跳舞"，LLM 按主体/动作/镜头/
光线/风格结构化扩写，并附负面词，生成模型对结构的响应远好于口语。
"""
import json
from typing import Optional

import httpx

from ..config import settings

SYSTEM_PROMPT = """你是一名专业的AI视频生成提示词工程师。用户会给你一段中文描述，你要把它扩写为
高质量的文生视频提示词，严格按以下JSON格式输出，不要输出任何其他内容：
{
  "optimized_prompt": "扩写后的提示词（中文，80-150字，包含：主体细节、动作与运动轨迹、
    镜头语言（推拉摇移/景别）、光线与氛围、画面风格、材质与质感）",
  "negative_prompt": "需要避免的元素（英文，逗号分隔，如: blurry, distorted, watermark, text）",
  "shot_suggestions": ["建议拆分的镜头描述1", "镜头描述2", "镜头描述3"]
}
扩写原则：
1. 忠于用户原意，不添加用户没提到的新主体，只做细节丰富
2. 运动描述要具体（方向、速度、幅度），这是视频质量的核心
3. 一次只描述一个场景/一个镜头，避免多场景混叙"""


SPLIT_SYSTEM_PROMPT = """你是一名专业影视导演。用户给你一段视频描述，你要把它拆分为指定数量的连续镜头，
用于AI视频分段生成后拼接成片。严格按以下JSON格式输出，不要输出任何其他内容：
{
  "shots": [
    {"prompt": "镜头1的完整描述（中文，60-120字）"},
    {"prompt": "镜头2的完整描述"},
    ...
  ]
}
拆分原则：
1. 镜头数量必须严格等于用户要求的数量，不多不少
2. 按叙事逻辑推进（开场建立场景 → 主体动作展开 → 高潮/收尾），前后镜头内容连贯
3. 每个镜头只描述一个场景，包含：主体+具体动作+景别（远景/中景/特写）+光线氛围
4. 忠于用户原意，不添加用户没提到的新主体
5. 相邻镜头用景别和视角变化制造节奏感（如全景→中景→特写），但主体形象、服装、环境风格保持一致"""


async def split_prompt_into_shots(user_prompt: str, shot_count: int) -> list[str]:
    """把单条描述拆成 N 个连贯镜头提示词，用于长视频分段生成"""
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法自动分镜")

    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": f"视频描述：{user_prompt}\n\n请拆分为 {shot_count} 个镜头。"},
        ],
        "temperature": 0.4,
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
        raise RuntimeError(f"LLM分镜结果无法解析: {content[:200]}")
    data = json.loads(text[start : end + 1])
    shots = [s["prompt"] for s in data.get("shots", []) if s.get("prompt")]
    if len(shots) != shot_count:
        # 数量不符时容忍：多了截断，少了用原描述补齐
        shots = shots[:shot_count]
        while len(shots) < shot_count:
            shots.append(user_prompt)
    return shots


async def optimize_prompt(user_prompt: str) -> dict:
    """返回 {optimized_prompt, negative_prompt, shot_suggestions}"""
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法使用提示词优化")

    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers=headers, json=body
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM服务错误 {resp.status_code}: {resp.text[:300]}")
        content = resp.json()["choices"][0]["message"]["content"]

    return _parse_json(content)


def _parse_json(content: str) -> dict:
    """LLM 可能带 ```json 包裹或前后废话，尽力解析"""
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
        "shot_suggestions": data.get("shot_suggestions", []),
    }
