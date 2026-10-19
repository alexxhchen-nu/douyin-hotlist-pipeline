"""抖音热榜蜘蛛（Scrapling 0.5）— 取热榜 Top N 关键词 + 每个关键词的 Top M 视频元数据。

原理：
  抖音 web 端的热榜和搜索结果都是页面加载后由 JS 调 API 拉取的，静态 HTML 里没有数据。
  所以这里用 AsyncStealthySession(record_requests=True) 开着真实浏览器加载页面，
  然后从 session.network 历史里捞 API 的 JSON 响应解析，不碰 X-Bogus/a_bogus 签名。

  2026-10 实测的两条硬事实：
  1) 热榜 API `aweme/v1/web/hot/search/list/` 匿名可用，但数据字段已改名 word_list
     （不是 hot_board_list），且匿名时 hot_value/view_count 被清零 —— 要真实热度需登录 Cookie。
  2) 搜索页 `/search/{kw}?type=video` 对匿名会话直接返回「验证码中间页」，不调搜索 API，
     必须带登录态 Cookie（含 sessionid）。登录后从 `aweme/v1/web/general/search/single/`
     网络响应取视频；万一接口改版改走 RSC 流，则兜底解析页面 HTML 里的
     self.__pace_f.push(...) flight 段。

登录态：
  默认自动读 .env 里的 DOUYIN_HOT_COOKIE（项目 login_export.py 从 BitBrowser 导出的格式），
  也可用 --cookies 直接传、或 --user-data-dir 指定带登录态的浏览器配置目录。

用法：
  python scripts/douyin_hot_spider.py                      # 默认 top50 关键词 × 每词 top10 视频
  python scripts/douyin_hot_spider.py --keywords 20 --videos 5
  python scripts/douyin_hot_spider.py --no-headless        # 调试时看浏览器
  python scripts/douyin_hot_spider.py --videos 0           # 只抓热榜关键词，不搜视频（快）
  python scripts/douyin_hot_spider.py --out out/douyin_hot

输出：<out>.json + <out>.csv，每条 item 带 type=hot|video。
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from scrapling.fetchers import AsyncStealthySession
from scrapling.spiders import Spider, Response

HOT_URL = "https://www.douyin.com/hot"
SEARCH_URL = "https://www.douyin.com/search/{kw}?type=video"

HOT_API_RE = re.compile(r"aweme/v1/web/hot/(search|detail)/list")
SEARCH_API_RE = re.compile(r"aweme/v1/web/(general/)?search/single")
CAPTCHA_TITLE = "验证码中间页"

LOGIN_COOKIE_MARKERS = ("sessionid", "sid_guard", "sid_tt", "uid_tt")


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


def _num(v, default=None):
    """字符串/数值统一转成数值；抖音 API 里的 hot_value 等字段是字符串。"""
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.replace(",", "").strip()
        try:
            return float(s) if "." in s else int(s)
        except ValueError:
            return default
    return default


def _walk_aweme(obj, out):
    """递归收集带 aweme_id+desc 的对象（RSC flight 里的 aweme 对象）。"""
    if isinstance(obj, dict):
        if isinstance(obj.get("aweme_id"), str) and "desc" in obj:
            out.append(obj)
        for v in obj.values():
            _walk_aweme(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_aweme(v, out)


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
        cookies: str = "",
        user_data_dir: str = "",
        **kwargs,
    ):
        # 基类 __init__ 内部会先调用 configure_sessions()，实例属性必须提前设好
        self.top_keywords = top_keywords
        self.top_videos = top_videos
        self.headless = headless
        self.user_data_dir = user_data_dir
        self._cookies = self._parse_cookies(cookies)
        self._cookie_injected = False
        self._captcha_warned = False
        self.browser_session: AsyncStealthySession | None = None
        super().__init__(**kwargs)

    # ---------- Cookie ----------

    @staticmethod
    def _parse_cookies(raw: str) -> list[dict]:
        """'a=1; b=2' 字符串 → Playwright 风格 cookie 列表（跳过非法值）。"""
        pairs = [p.split("=", 1) for p in raw.split(";") if "=" in p]
        out = []
        for name, value in pairs:
            name, value = name.strip(), value.strip()
            if not name or not value:
                continue
            out.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
        return out

    @staticmethod
    def _load_cookies_from_env() -> str:
        """读项目 .env 的 DOUYIN_HOT_COOKIE（兼容 login_export.py 的导出格式）。"""
        env_path = Path(".env")
        if not env_path.exists():
            return ""
        env = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        return env.get("DOUYIN_HOT_COOKIE", "")

    def _has_login_cookies(self) -> bool:
        names = {c["name"].lower() for c in self._cookies}
        return any(any(m in n for n in names) for m in LOGIN_COOKIE_MARKERS)

    async def _setup_page(self, page):
        """每个页面导航前执行：把 Cookie 注入浏览器上下文（只注入一次）。"""
        if self._cookies and not self._cookie_injected:
            try:
                await page.context.add_cookies(self._cookies)
                self._cookie_injected = True
                self.logger.info("已注入 %d 个 Cookie（登录态=%s）", len(self._cookies), self._has_login_cookies())
            except Exception as e:  # noqa: BLE001
                self.logger.warning("Cookie 注入失败: %s", e)

    # ---------- 会话 ----------

    def configure_sessions(self, manager):
        kw = dict(
            headless=self.headless,
            network_idle=True,       # 等页面网络静默，保证 API 调用完成并被记录
            record_requests=True,    # 记录会话内所有请求/响应
            max_pages=self.concurrent_requests,
            timeout=60000,
            wait=1500,
            google_search=False,     # 不给抖音伪造 Google referer
            page_setup=self._setup_page,
        )
        if self.user_data_dir:
            kw["user_data_dir"] = self.user_data_dir
        self.browser_session = AsyncStealthySession(**kw)
        manager.add("browser", self.browser_session, default=True)

    # ---------- 网络历史里的 JSON ----------

    def _recorded_json(self):
        """遍历会话记录的 XHR/fetch 响应，逐个尝试解析成 dict。"""
        for resp in self.browser_session.network.search(
            resource_type="xhr", limit=None, include_static=False
        ):
            if resp.status == 200:
                try:
                    data = resp.json()
                except Exception:
                    continue
                if isinstance(data, dict):
                    yield resp.url, data
        for resp in self.browser_session.network.search(
            resource_type="fetch", limit=None, include_static=False
        ):
            if resp.status == 200:
                try:
                    data = resp.json()
                except Exception:
                    continue
                if isinstance(data, dict):
                    yield resp.url, data

    # ---------- 解析热榜 ----------

    def _parse_hotlist(self) -> list[dict]:
        """从记录的 API 响应里找热榜 JSON，取 Top N 关键词。

        数据字段按 2026-10 实测是 data.word_list；hot_board_list 是旧版字段，
        再不行就泛化扫描任何含 word 的对象列表。
        """
        candidates = []
        for url, data in self._recorded_json():
            inner = data.get("data")
            if not isinstance(inner, dict):
                continue
            for key in ("word_list", "hot_board_list", "trending_list"):
                val = inner.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict) and "word" in val[0]:
                    candidates.append((url, val))
                    break
            else:
                for key, val in inner.items():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        if "word" in val[0] and any(k in val[0] for k in ("position", "hot_value", "view_count")):
                            candidates.append((url, val))
                            break
        if not candidates:
            return []

        board = next((b for u, b in candidates if HOT_API_RE.search(u)), candidates[0][1])
        rows = []
        for it in board:
            if not isinstance(it, dict) or not it.get("word"):
                continue
            hot_value = _num(it.get("hot_value"))
            rows.append({
                "type": "hot",
                "rank": _num(it.get("position")) or (len(rows) + 1),
                "title": it["word"].strip(),
                "word": it["word"].strip(),
                "hot_value": hot_value,
                "hot_value_k": round(hot_value / 1000, 1) if isinstance(hot_value, (int, float)) else "",
                "label": it.get("label", ""),
                "sentence_id": it.get("sentence_id", ""),
                "view_count": _num(it.get("view_count"), default=""),
                "discuss_video_count": _num(it.get("discuss_video_count"), default=""),
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            })
        rows.sort(key=lambda r: r["rank"])
        return rows[: self.top_keywords]

    # ---------- 解析视频 ----------

    def _extract_video(self, item: dict, keyword: str) -> dict:
        info = _first(item, "aweme_info", "aweme", default=item)
        if not isinstance(info, dict):
            return {}
        video = info.get("video") or {}
        stats = info.get("statistics") or {}
        author = info.get("author") or {}
        return {
            "type": "video",
            "keyword": keyword,
            "video_rank": 0,  # 由调用方按顺序填
            "aweme_id": info.get("aweme_id", ""),
            "desc": (info.get("desc") or "").strip(),
            "author": author.get("nickname", ""),
            "author_uid": author.get("unique_id", ""),
            "digg_count": _num(stats.get("digg_count"), default=0),
            "comment_count": _num(stats.get("comment_count"), default=0),
            "share_count": _num(stats.get("share_count"), default=0),
            "collect_count": _num(stats.get("collect_count"), default=0),
            "play_count": _num(stats.get("play_count"), default=0),
            "duration_ms": _num(info.get("duration"), default=0),
            "width": _num(video.get("width"), default=0),
            "height": _num(video.get("height"), default=0),
            "play_url": _first(video, "play_addr.url_list.0", default=""),
            "cover_url": _first(video, "cover.url_list.0", default=""),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _rsc_aweme_objects(text: str) -> list[dict]:
        """从页面 HTML 的 self.__pace_f.push flight 段里挖 aweme 对象（接口改走 RSC 时兜底）。"""
        found = []
        for m in re.finditer(r'self\.__pace_f\.push\(\[(\d+),\s*("(?:[^"\\]|\\.)*")\]\)', text):
            try:
                seg = json.loads(m.group(2))
            except Exception:
                continue
            if not isinstance(seg, str):
                continue
            # RSC flight 前缀形如 "1:I{...}" 或 "2:J0,{...}"，从第一个 { 或 [ 切起
            start = min(i for i in (seg.find("{"), seg.find("[")) if i != -1) if ("{" in seg or "[" in seg) else -1
            if start == -1:
                continue
            try:
                data = json.loads(seg[start:])
            except Exception:
                continue
            _walk_aweme(data, found)
        seen, out = set(), []
        for d in found:
            aid = d.get("aweme_id")
            if aid in seen:
                continue
            seen.add(aid)
            out.append(d)
        return out

    def _parse_videos(self, keyword: str, page_doc_text: str) -> list[dict]:
        """从记录的搜索 API 响应 + 页面 RSC 里捞该关键词的视频，取 Top M 条。"""
        kw_enc = urllib.parse.quote(keyword)
        api_items = []
        for url, data in self._recorded_json():
            if not SEARCH_API_RE.search(url):
                continue
            if kw_enc not in url and keyword not in urllib.parse.unquote(url):
                continue
            items = data.get("data") or []
            if isinstance(items, list) and items:
                api_items.extend(items)
        # 万一 URL 里的 keyword 编码规则对不上，且历史上只有一条搜索 API，就用它
        if not api_items:
            all_search = [d for u, d in self._recorded_json() if SEARCH_API_RE.search(u)]
            if len({id(d) for d in all_search}) == 1 and isinstance((all_search[0] or {}).get("data"), list):
                api_items = all_search[0]["data"]

        rsc_items = self._rsc_aweme_objects(page_doc_text)

        seen, rows = set(), []
        for item in list(api_items) + list(rsc_items):
            if not isinstance(item, dict):
                continue
            row = self._extract_video(item, keyword)
            if not row or row["aweme_id"] in seen:
                continue
            seen.add(row["aweme_id"])
            row["video_rank"] = len(rows) + 1
            rows.append(row)
            if len(rows) >= self.top_videos:
                break
        return rows

    def _page_is_captcha(self, doc_text: str) -> bool:
        return CAPTCHA_TITLE in doc_text or "验证码" in doc_text

    # ---------- 回调 ----------

    async def parse(self, response: Response):
        """热榜页：解析 Top N 关键词，然后为每个关键词派发搜索请求。"""
        self.logger.info("热榜页加载完成: %s (status=%s)", response.url, response.status)
        hot = self._parse_hotlist()
        if not hot:
            self.logger.error("没从网络历史里解析到热榜数据（可能被验证码拦截或 API 路径变了）")
            return

        if not self._cookies:
            self.logger.warning("未提供 Cookie：热榜热度值会被清零；搜索视频会被验证码墙拦截")
        elif not self._has_login_cookies():
            self.logger.warning(
                "Cookie 里没有 sessionid/sid_guard 等登录态标记，搜索视频大概率仍会被验证码拦截。"
                "用 login_export.py 从 BitBrowser 导出登录 Cookie 写入 .env 的 DOUYIN_HOT_COOKIE"
            )

        self.logger.info("解析到 %d 个热榜关键词", len(hot))
        for item in hot:
            yield item
            if self.top_videos <= 0:
                continue
            kw = item["word"]
            url = SEARCH_URL.format(kw=urllib.parse.quote(kw, safe=""))
            yield response.follow(
                url,
                callback=self.parse_videos,
                meta={"keyword": kw, "hot_rank": item["rank"]},
            )

    async def parse_videos(self, response: Response):
        """搜索页：从网络历史 + 页面 RSC 里捞该关键词的视频，取 Top M 条。"""
        kw = response.meta.get("keyword", "")
        doc_text = response.body.decode("utf-8", errors="ignore")

        if self._page_is_captcha(doc_text):
            if not self._captcha_warned:
                self._captcha_warned = True
                self.logger.warning(
                    "搜索页返回验证码中间页：抖音对匿名会话的搜索做了风控，"
                    "请用 login_export.py 导出登录 Cookie（需含 sessionid）写入 .env 的 DOUYIN_HOT_COOKIE"
                )
            return

        videos = self._parse_videos(kw, doc_text)
        self.logger.info("关键词「%s」解析到 %d 个视频", kw, len(videos))
        for item in videos:
            item["hot_rank"] = response.meta.get("hot_rank")
            yield item


def main():
    ap = argparse.ArgumentParser(description="抖音热榜蜘蛛：Top N 关键词 × 每词 Top M 视频")
    ap.add_argument("--keywords", type=int, default=50, help="热榜取多少个关键词（默认 50）")
    ap.add_argument("--videos", type=int, default=10, help="每个关键词取多少条视频（默认 10）；0=只抓热榜不搜视频")
    ap.add_argument("--out", default="out/douyin_hot", help="输出文件前缀（生成 .json/.csv）")
    ap.add_argument("--cookies", default="", help="Cookie 串 'a=1; b=2'（默认读 .env 的 DOUYIN_HOT_COOKIE）")
    ap.add_argument("--user-data-dir", default="", help="带登录态的浏览器配置目录（可选）")
    ap.add_argument("--headless", dest="headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    cookies = args.cookies
    if not cookies:
        cookies = DouyinHotSpider._load_cookies_from_env()

    spider = DouyinHotSpider(
        top_keywords=args.keywords,
        top_videos=args.videos,
        headless=args.headless,
        cookies=cookies,
        user_data_dir=args.user_data_dir,
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
    if videos and kw_count:
        missing = [h["word"] for h in hot if h["word"] not in kw_count]
        print(f"[!] 有 {len(missing)} 个关键词没解析到视频（如 {missing[:3]}）")


if __name__ == "__main__":
    main()
