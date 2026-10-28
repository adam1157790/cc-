"""视频文件处理：下载厂商返回的临时URL → 本地落盘；抽封面帧。

ffmpeg 二进制来自 imageio-ffmpeg 包（pip 自动附带），无需系统安装。
"""
import asyncio
import subprocess
from pathlib import Path

import httpx


def get_ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


async def download_video(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"下载视频失败 HTTP {resp.status_code}")
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    return dest


def extract_cover(video: Path, dest: Path, at_second: float = 0.5) -> Path:
    """抽取封面帧（默认第0.5秒，避开纯黑首帧）"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        get_ffmpeg(), "-y", "-ss", str(at_second), "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(dest),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000,
    )
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"抽帧失败: {proc.stderr[-300:]}")
    return dest


def concat_videos(videos: list[Path], dest: Path, transition: str = "fade", duration: float = 0.5) -> Path:
    """分镜拼接：统一转码后用 xfade 交叉转场衔接（默认 0.5s 叠化，无硬切）。

    transition 可选 ffmpeg xfade 转场名（fade=叠化/smoothleft/wiperight 等）；
    duration<=0 或单镜头时退化为 concat 硬切。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # 1. 统一转码：相同编码/分辨率/帧率/像素格式（xfade 的硬性要求）
        normalized: list[Path] = []
        for i, v in enumerate(videos):
            norm = tmp_dir / f"norm_{i:03d}.mp4"
            cmd = [
                get_ffmpeg(), "-y", "-i", str(v),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-an", "-r", "30", str(norm),
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=0x08000000,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"镜头{i}转码失败: {proc.stderr[-300:]}")
            normalized.append(norm)

        # 2. 无转场模式：concat demuxer 硬切
        if not transition or duration <= 0 or len(normalized) == 1:
            list_file = tmp_dir / "list.txt"
            list_file.write_text(
                "\n".join(f"file '{str(p).replace(chr(92), '/')}'" for p in normalized), encoding="utf-8"
            )
            cmd = [
                get_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file), "-c", "copy", str(dest),
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=0x08000000,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"拼接失败: {proc.stderr[-300:]}")
            return dest

        # 3. 读各片段实际时长，不足转场长度则尾部冻帧补齐（tpad）
        durations = [_probe_duration(p) for p in normalized]
        for i in range(len(normalized) - 1):
            if durations[i] < duration + 0.2:
                pad_s = duration + 0.2 - durations[i]
                padded = tmp_dir / f"pad_{i:03d}.mp4"
                cmd = [
                    get_ffmpeg(), "-y", "-i", str(normalized[i]),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={pad_s:.2f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-an", "-r", "30", str(padded),
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=0x08000000,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"镜头{i}补帧失败: {proc.stderr[-300:]}")
                normalized[i] = padded
                durations[i] = duration + 0.2

        # 4. 构造 xfade 链：[0][1]xfade→[v1]; [v1][2]xfade→[v2]; ...
        inputs: list[str] = []
        for p in normalized:
            inputs += ["-i", str(p)]
        filter_parts = []
        prev = "0:v"
        offset = 0.0
        for i in range(1, len(normalized)):
            offset += durations[i - 1] - duration  # 转场起点 = 已播放总长 - 重叠
            out = f"v{i}"
            filter_parts.append(
                f"[{prev}][{i}:v]xfade=transition={transition}:duration={duration}:offset={offset:.3f}[{out}]"
            )
            prev = out
        cmd = [
            get_ffmpeg(), "-y", *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{prev}]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", "-r", "30", str(dest),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=0x08000000,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"转场拼接失败: {proc.stderr[-300:]}")
    return dest


def _probe_duration(video: Path) -> float:
    """从 ffmpeg 日志解析时长（imageio-ffmpeg 不带 ffprobe，用这个替代）"""
    cmd = [get_ffmpeg(), "-i", str(video)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000,
    )
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        raise RuntimeError(f"无法读取视频时长: {video}")
    h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mnt * 60 + s
