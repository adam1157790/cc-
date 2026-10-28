"""仅用于本地冒烟测试的假引擎：直接返回一个可下载的示例视频URL。"""
from .base import PollResult, SubmitResult, VideoProvider

# 一个公网测试视频（Big Buck Bunny 片段）
FAKE_VIDEO = "https://download.samplelib.com/mp4/sample-5s.mp4"


class MockProvider(VideoProvider):
    name = "mock"
    supports_i2v = True
    supported_durations = (5, 10)
    supported_ratios = ("16:9", "9:16")

    async def submit(self, prompt, *, duration=5, aspect_ratio="16:9", seed=None, image_path=None):
        return SubmitResult(provider_task_id=f"mock_{seed}")

    async def poll(self, provider_task_id):
        return PollResult("succeeded", 100, video_url=FAKE_VIDEO)
