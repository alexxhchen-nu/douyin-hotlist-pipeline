"""抖音热榜蜘蛛（Scrapling 0.5）— 取热榜 Top N 关键词 + 每个关键词的 Top M 视频元数据。

原理：
  抖音 web 端的热榜和搜索结果都是页面加载后由 JS 调 API 拉取的，
  静态 HTML 里没有数据。所以这里用 AsyncStealthySession(record_requests=True)
  开着真实浏览器加载页面，然后直接从 session.network 历史里捞出 API 的 JSON 响应解析，
  不碰 X-Bogus/a_bogus 签名（签名由页面 JS 自己算好）。

用法：
  python scripts/douyin_hot_spider.py                      # 默认 top50 关键词 × 每词 top10 视频
  python scripts/douyin_hot_spider.py --keywords 20 --videos 5
  python scripts/douyin_hot_spider.py --no-headless        # 调试时看浏览器
  python scripts/douyin_hot_spider.py --out out/douyin_hot

输出：<out>.json + <out>.csv，每条 item 带 type=hot|video。
"""
from __future__ import annotations

import argparse
import logging
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from scrapling.fetchers import AsyncStealthySession
from scrapling.spiders import Spider, Response

HOT_URL = "https://www.douyin.com/hot"
SEARCH_URL = "https://www.douyin.com/search/{kw}?type=video"

# 热榜 API / 搜索结果 API 的 URL 特征（万一抖音改路径，泛化扫描兜底）
HOT_API_RE = re.compile(r"aweme/v1/web/hot/(search|detail)/list")
SEARCH_API_RE = re.compile(r"aweme/v1/web/general/search/single")


def _get_path(obj: dict, path: str, default=None):
    """'a.b.0' 式取值（支持列表下标），任何一层缺失都返回 default。"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return default
        if cur is None:
            return default
    return cur


def _first(obj: dict, *paths, default=None):
    for p in paths:
        v = _get_path(obj, p)
        if v not in (None, "", [], {}):
            return v
    return default


class DouyinHotSpider(Spider):
    name = "douyin_hot"
    start_urls = [HOT_URL]
    concurrent_requests = 4
    download_delay = 1.0
    # douyin.com 的 robots.txt 全面封禁爬虫，本项目（热榜采集管线）已获授权采集，
    # 故不开启 robots_txt_obey。
    robots_txt_obey = False

    def __init__(
        self,
        top_keywords: int = 50,
        top_videos: int = 10,
        headless: bool = True,
        **kwargs,
    ):
        # 基类 __init__ 内部会先调用 configure_sessions()，实例属性必须提前设好
        self.top_keywords = top_keywords
        self.top_videos = top_videos
        self.headless = headless
        self.browser_session: AsyncStealthySession | None = None
        super().__init__(**kwargs)

    def configure_sessions(self, manager):
        self.browser_session = AsyncStealthySession(
            headless=self.headless,
            network_idle=True,          # 等页面网络静默，保证 API 调用完成并被记录
            record_requests=True,       # 记录会话内所有请求/响应
            max_pages=self.concurrent_requests,
            timeout=45000,
            wait=1500,                  # 页面加载完再等一会儿，防丢尾部请求
        )
        manager.add("browser", self.browser_session, default=True)

    # ---------- 网络历史里的 JSON 挖掘 ----------

    def _recorded_json(self):
        """遍历会话记录的 XHR/fetch 响应，逐个尝试解析成 dict。"""
        for resp in self.browser_session.network.search(
            resource_type="xhr", limit=None, include_static=False
        ):
            if resp.status != 200:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            if isinstance(data, dict):
                yield resp.url, data
        for resp in self.browser_session.network.search(
            resource_type="fetch", limit=None, include_static=False
        ):
            if resp.status != 200:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            if isinstance(data, dict):
                yield resp.url, data

    # ---------- 解析热榜 ----------

    def _parse_hotlist(self) -> list[dict]:
        """从记录的 API 响应里找热榜 JSON，取 Top N 关键词。

        优先精确匹配 hot/search/list，找不到就泛化扫描：
        任何包含 hot_board_list 键、或含 word+position 对象列表的 JSON 都认。
        """
        candidates = []
        for url, data in self._recorded_json():
            board = _get_path(data, "data.hot_board_list")
            if isinstance(board, list) and board:
                candidates.append((url, board))
                continue
            if _get_path(data, "hot_board_list") is not None:
                candidates.append((url, _get_path(data, "hot_board_list")))
                continue
            # 泛化兜底：data 下某个列表里的元素同时带 word/position
            inner = data.get("data")
            if isinstance(inner, dict):
                for key, val in inner.items():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        if all("word" in it and ("position" in it or "hot_value" in it) for it in val):
                            candidates.append((url, val))
        if not candidates:
            return []

        # 优先精确 API 的响应，否则用第一个找到的
        board = next((b for u, b in candidates if HOT_API_RE.search(u)), candidates[0][1])
        rows = []
        for it in board:
            if not isinstance(it, dict) or not it.get("word"):
                continue
            hot_value = it.get("hot_value")
            rows.append({
                "type": "hot",
                "rank": it.get("position") or it.get("rank") or (len(rows) + 1),
                "title": it["word"].strip(),
                "word": it["word"].strip(),
                "hot_value": hot_value,
                "hot_value_k": round(hot_value / 1000, 1) if isinstance(hot_value, (int, float)) else "",
                "label": it.get("label", ""),
                "sentence_id": it.get("sentence_id", ""),
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            })
        rows.sort(key=lambda r: r["rank"])
        return rows[: self.top_keywords]

    # ---------- 解析每个关键词的视频 ----------

    def _parse_videos(self, keyword: str) -> list[dict]:
        """从记录的搜索 API 响应里捞该关键词的结果，取 Top M 条视频元数据。"""
        kw_enc = urllib.parse.quote(keyword)
        matches = []
        for url, data in self._recorded_json():
            # 只认搜索结果 API；用 URL 里的 keyword 参数精确匹配当前关键词
            if not SEARCH_API_RE.search(url):
                continue
            if kw_enc not in url and keyword not in urllib.parse.unquote(url):
                continue
            items = data.get("data") or []
            if isinstance(items, list) and items:
                matches.append((url, items))

        items = matches[0][1] if matches else []
        rows = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # 搜索条目里视频对象在 aweme_info；接口改版时兜底 aweme / video
            info = _first(it, "aweme_info", "aweme", default=it)
            if not isinstance(info, dict):
                continue
            video = info.get("video") or {}
            stats = info.get("statistics") or {}
            author = info.get("author") or {}
            play_url = _first(video, "play_addr.url_list.0", default="")
            cover_url = _first(video, "cover.url_list.0", default="")
            rows.append({
                "type": "video",
                "keyword": keyword,
                "video_rank": len(rows) + 1,
                "aweme_id": info.get("aweme_id", ""),
                "desc": (info.get("desc") or "").strip(),
                "author": author.get("nickname", ""),
                "author_uid": author.get("unique_id", ""),
                "digg_count": stats.get("digg_count", 0),
                "comment_count": stats.get("comment_count", 0),
                "share_count": stats.get("share_count", 0),
                "collect_count": stats.get("collect_count", 0),
                "play_count": stats.get("play_count", 0),
                "duration_ms": info.get("duration", 0),
                "width": video.get("width", 0),
                "height": video.get("height", 0),
                "play_url": play_url,
                "cover_url": cover_url,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            })
        return rows[: self.top_videos]

    # ---------- 回调 ----------

    async def parse(self, response: Response):
        """热榜页：解析 Top N 关键词，然后为每个关键词派发搜索请求。"""
        self.logger.info("热榜页加载完成: %s (status=%s)", response.url, response.status)
        hot = self._parse_hotlist()
        if not hot:
            self.logger.error("没从网络历史里解析到热榜数据（可能被验证码拦截或 API 路径变了）")
            return

        self.logger.info("解析到 %d 个热榜关键词", len(hot))
        for item in hot:
            yield item
            kw = item["word"]
            url = SEARCH_URL.format(kw=urllib.parse.quote(kw, safe=""))
            yield response.follow(
                url,
                callback=self.parse_videos,
                meta={"keyword": kw, "hot_rank": item["rank"]},
            )

    async def parse_videos(self, response: Response):
        """搜索页：从网络历史里捞该关键词的搜索结果 API，取 Top M 视频。"""
        kw = response.meta.get("keyword", "")
        videos = self._parse_videos(kw)
        self.logger.info(
            "关键词「%s」解析到 %d 个视频 (status=%s)",
            kw,
            len(videos),
            response.status,
        )
        for item in videos:
            item["hot_rank"] = response.meta.get("hot_rank")
            yield item


def main():
    ap = argparse.ArgumentParser(description="抖音热榜蜘蛛：Top N 关键词 × 每词 Top M 视频")
    ap.add_argument("--keywords", type=int, default=50, help="热榜取多少个关键词（默认 50）")
    ap.add_argument("--videos", type=int, default=10, help="每个关键词取多少条视频（默认 10）")
    ap.add_argument("--out", default="out/douyin_hot", help="输出文件前缀（生成 .json/.csv）")
    ap.add_argument("--headless", dest="headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    spider = DouyinHotSpider(
        top_keywords=args.keywords,
        top_videos=args.videos,
        headless=args.headless,
    )
    result = spider.start()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.items.to_json(f"{out}.json", indent=True)
    result.items.to_csv(f"{out}.csv")

    hot = [i for i in result.items if i.get("type") == "hot"]
    videos = [i for i in result.items if i.get("type") == "video"]
    print(f"[ok] 热榜关键词 {len(hot)} 个 / 视频条目 {len(videos)} 条")
    print(f"[ok] 输出: {out}.json, {out}.csv")
    print(f"[ok] 请求 {result.stats.requests_count} 个，耗时 {result.stats.elapsed_seconds:.1f}s")
    for h in hot[:5]:
        print(f"  #{h['rank']:>2} {h['title']}  ({h['hot_value_k']}K热度)")
    kw_count = {}
    for v in videos:
        kw_count[v["keyword"]] = kw_count.get(v["keyword"], 0) + 1
    for kw, n in list(kw_count.items())[:5]:
        print(f"  「{kw}」: {n} 条视频")


if __name__ == "__main__":
    main()
