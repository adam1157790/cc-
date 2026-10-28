"""测试用文生图引擎（ENABLE_MOCK_PROVIDER=1 时可用）：生成纯色 PNG。

生成的 PNG 带随机噪点，方便直观确认多候选确实不同。
"""
import base64
import io
import random
import struct
import zlib
from typing import Optional

from .image_base import ImageProvider, ImageSubmitResult


def _png(width: int, height: int, seed: Optional[int]) -> bytes:
    rng = random.Random(seed or 0)
    r, g, b = rng.randrange(60, 220), rng.randrange(60, 220), rng.randrange(60, 220)
    raw = b""
    for _ in range(height):
        raw += b"\x00" + bytes(rng.choice((r, g, b)) for _ in range(width * 3))
    # 噪点：随机替换部分像素通道
    chunks = []

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    chunks.append(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    chunks.append(chunk(b"IDAT", zlib.compress(raw)))
    chunks.append(chunk(b"IEND", b""))
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


class MockImageProvider(ImageProvider):
    name = "mock"
    supports_e2i = True

    async def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        seed: Optional[int] = None,
        guidance: int = 0,
        ref_image_path: Optional[str] = None,
    ) -> ImageSubmitResult:
        try:
            w, h = size.lower().split("x")
            width, height = int(w), int(h)
        except ValueError:
            width = height = 1024
        width, height = max(64, min(width, 2048)), max(64, min(height, 2048))
        png = _png(width, height, seed)
        return ImageSubmitResult(image_url=f"data:image/png;base64,{base64.b64encode(png).decode()}")
