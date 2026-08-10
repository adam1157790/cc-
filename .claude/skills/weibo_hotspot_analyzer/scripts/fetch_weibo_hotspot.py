#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微博热搜抓取器 (Weibo Hotspot Fetcher)

抓取微博实时热搜，输出结构化 JSON 供 weibo_hotspot_analyzer skill 分析。
无第三方依赖，仅用 Python 标准库。依次尝试多个数据源，取第一个成功的结果。

用法:
    python fetch_weibo_hotspot.py [--top N] [--raw]

输出（stdout，JSON）:
    {
      "source": "数据源名称",
      "fetched_at": "北京时间时间戳",
      "count": 条数,
      "items": [
        {"rank": 排名, "word": "热搜词", "num": 热度值,
         "label": "上榜标签(如 新/沸)", "is_boom": 是否爆,
         "category": "原始分类码", "scheme": "跳转链接"}
      ]
    }
"""

import argparse
import gzip
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# Windows 控制台默认用 GBK 输出，会破坏中文；强制 stdout/stderr 用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://weibo.com/hot/search",
}

# 时间戳时区：微博显示为北京时间
CN_TZ = timezone(timedelta(hours=8))


def _parse_weibo_ajax(data):
    """微博官方 ajax 接口：https://weibo.com/ajax/side/hotSearch"""
    items = []
    realtime = data.get("data", {}).get("realtime", []) or []
    for item in realtime:
        if not item.get("word") or item.get("is_ad"):
            continue
        items.append({
            "rank": len(items) + 1,
            "word": item.get("word", ""),
            "num": item.get("num", 0),
            "label": item.get("label_name", ""),
            "is_boom": bool(item.get("is_boom")),
            "category": item.get("category", ""),
            "scheme": item.get("word_scheme", ""),
        })
    return items


def _parse_hot_band(data):
    """微博 hot band 接口：https://weibo.com/ajax/statuses/hot_band"""
    items = []
    band_list = data.get("data", {}).get("band_list", []) or []
    for item in band_list:
        if not item.get("note"):
            continue
        items.append({
            "rank": len(items) + 1,
            "word": item.get("note", ""),
            "num": item.get("num", 0),
            "label": item.get("label_name", ""),
            "is_boom": bool(item.get("is_boom")),
            "category": item.get("category", ""),
            "scheme": item.get("scheme", ""),
        })
    return items


def _parse_vvhan(data):
    """公共聚合接口：https://api.vvhan.com/api/hotlist/wbHot"""
    items = []
    for item in data.get("data", []) or []:
        if not item.get("title"):
            continue
        items.append({
            "rank": len(items) + 1,
            "word": item.get("title", ""),
            "num": item.get("hot", 0),
            "label": "",
            "is_boom": False,
            "category": "",
            "scheme": item.get("url", ""),
        })
    return items


SOURCES = [
    {"name": "weibo_ajax_hotsearch",
     "url": "https://weibo.com/ajax/side/hotSearch",
     "parser": _parse_weibo_ajax},
    {"name": "weibo_hot_band",
     "url": "https://weibo.com/ajax/statuses/hot_band",
     "parser": _parse_hot_band},
    {"name": "vvhan_public_api",
     "url": "https://api.vvhan.com/api/hotlist/wbHot",
     "parser": _parse_vvhan},
]


def fetch_bytes(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return raw


def decode(raw):
    # utf-8-sig 自动去掉 BOM
    return raw.decode("utf-8-sig", errors="replace")


def main():
    ap = argparse.ArgumentParser(description="抓取微博热搜")
    ap.add_argument("--top", type=int, default=50, help="返回条数（默认 50）")
    ap.add_argument("--raw", action="store_true", help="附加原始响应前 2000 字符便于排查")
    args = ap.parse_args()

    errors = []
    for src in SOURCES:
        try:
            raw = fetch_bytes(src["url"])
            data = json.loads(decode(raw))
            items = src["parser"](data)
            if not items:
                raise ValueError("解析结果为空")
            items = items[: args.top]
            result = {
                "source": src["name"],
                "fetched_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(items),
                "items": items,
            }
            if args.raw:
                result["raw_preview"] = decode(raw)[:2000]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as e:  # noqa: BLE001 —— 数据源容错，全部失败才报错
            errors.append(f"{src['name']}: {e}")
            continue

    print(json.dumps({"success": False, "errors": errors, "items": []},
                     ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
