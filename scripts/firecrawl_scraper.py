"""Firecrawl provider: managed-browser scraping for Douyin search pages.

This provider still needs douyin_state.json so the request carries the same
session cookies as the local Playwright flow. Firecrawl renders the page remotely
and we ask it to return a structured JSON list; the video bytes are still fetched
by the Cloudflare Worker downloader in downloader.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import DOUYIN_HOT_COOKIE, FIRECRAWL_API_KEY, FIRECRAWL_API_URL, STATE_FILE

EXTRACT_PROMPT = (
    "Extract all video search results shown on this Douyin search page. "
    "Return a JSON object with a top-level \"videos\" array. "
    "Each item must have video_id, title, author, play_url and detail_url. "
    "Skip navigation, suggested accounts, ads and empty cards."
)

SCROLL_ACTIONS = [
    {"type": "wait", "milliseconds": 1500},
    {"type": "scroll", "direction": "down"},
    {"type": "wait", "milliseconds": 1200},
    {"type": "scroll", "direction": "down"},
    {"type": "wait", "milliseconds": 1200},
]


class FirecrawlAuthRequired(RuntimeError):
    pass


def _load_state() -> dict:
    path = Path(STATE_FILE)
    if not path.exists():
        raise FirecrawlAuthRequired(
            "douyin_state.json 不存在。先运行 python login_export.py --bit "
            "导出抖音登录态，Firecrawl provider 才能注入会话 Cookie。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def cookie_header() -> str:
    # 优先使用 .env 里配置的 DOUYIN_HOT_COOKIE（hot 页/search 页通用），
    # 没有则回退到 douyin_state.json 里的 dy cookie。
    if DOUYIN_HOT_COOKIE:
        return DOUYIN_HOT_COOKIE
    state = _load_state()
    cookies = []
    for item in state.get("cookies", []):
        domain = item.get("domain", "")
        if domain.endswith("douyin.com") or "douyin.com" in domain:
            cookies.append(f"{item.get('name', '')}={item.get('value', '')}")
    if not cookies:
        raise FirecrawlAuthRequired("douyin_state.json 里没有可用的 douyin.com Cookie。")
    return "; ".join(cookies)


def _client():
    if not FIRECRAWL_API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY 未配置，请写入 .env")
    from firecrawl import Firecrawl
    return Firecrawl(api_key=FIRECRAWL_API_KEY, api_url=FIRECRAWL_API_URL)


def _as_video(item: dict) -> dict | None:
    video_id = str(item.get("video_id") or item.get("aweme_id") or "").strip()
    detail_url = str(item.get("detail_url") or item.get("url") or "").strip()
    if not video_id:
        m = re.search(r"/video/(\d+)", detail_url)
        if m:
            video_id = m.group(1)
    if not video_id:
        return None

    play_url = str(item.get("play_url") or "").strip()
    if play_url.startswith("//"):
        play_url = "https:" + play_url
    return {
        "video_id": video_id,
        "title": str(item.get("title") or "").strip(),
        "author": str(item.get("author") or "").strip(),
        "play_url": play_url,
        "detail_url": detail_url,
    }


def _extract_videos(payload) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("videos", "results", "items", "data", "aweme_list"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in (_as_video(v) for v in val if isinstance(v, dict)) if r]
    if isinstance(payload, list):
        return [r for r in (_as_video(v) for v in payload if isinstance(v, dict)) if r]
    return []


def scrape_keyword_firecrawl(keyword: str, max_videos: int) -> list[dict]:
    from urllib.parse import quote

    from config import DEFAULT_UA

    client = _client()
    url = f"https://www.douyin.com/search/{quote(keyword)}?type=video"
    headers = {"User-Agent": DEFAULT_UA, "Cookie": cookie_header()}

    doc = client.scrape(
        url,
        formats=[
            "markdown",
            {"type": "json", "prompt": EXTRACT_PROMPT},
        ],
        actions=SCROLL_ACTIONS,
        headers=headers,
        timeout=60000,
    )

    videos = []
    json_payload = getattr(doc, "json", None)
    if json_payload:
        videos = _extract_videos(json_payload)
    if not videos:
        raw_html = getattr(doc, "raw_html", None) or getattr(doc, "html", None)
        if isinstance(raw_html, str):
            ids = re.findall(r'"aweme_id"\s*:\s*"(\d+)"', raw_html)
            videos = [{"video_id": vid, "title": "", "author": "", "play_url": "", "detail_url": ""} for vid in dict.fromkeys(ids)]

    seen = {}
    for video in videos:
        seen.setdefault(video["video_id"], video)
    return list(seen.values())[:max_videos]