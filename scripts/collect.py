"""抖音热榜 → top10 视频 采集闭环（忽略 R2）。

每 65 分钟一轮：
  1) Firecrawl 抓 douyin.com/hot（DOUYIN_HOT_COOKIE）→ 50 个热榜关键词
  2) 每个关键词抓 top N 视频（默认 10）
  3) 全部落到本地 CSV（忽略 R2 / Worker 下载）

视频抓取 provider：
  - local   使用本地 Playwright 拦截搜索 API（现有 scraper.py 的登录态，
            需要 douyin_state.json；无登录态时报错）
  - firecrawl  使用 Firecrawl 搜索页抓取（当前被抖音滑块验证码拦截，
            实测返回验证码占位；作为降级实验，失败会记录到输出）

用法：
  python collect.py --rounds 1 --mode dry
  python collect.py --rounds 1 --mode real --provider firecrawl
  python collect.py --loop --interval-min 65   # 无限循环，每 65 分钟一轮
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import time
from pathlib import Path

from config import DOUYIN_HOT_COOKIE, STATE_FILE
from hotlist import fetch_hot_markdown, parse_hotlist

# 登录态标识：抖音真正登录的 cookie 里应包含这些之一
LOGIN_COOKIE_MARKERS = ("sessionid", "sessionid_ss", "odin_tt", "passport_csrf_token", "sid_guard", "uid_tt")


OUT_DIR = Path(__file__).parent / "out"

# ---- 视频抓取 provider ----

try:
    from scraper import LoginRequired, open_context, scrape_keyword as _scrape_local
    HAS_LOCAL = True
except Exception:
    HAS_LOCAL = False


def scrape_videos_local(keyword: str, max_videos: int) -> list[dict]:
    """本地 Playwright 拦截搜索 API（需要 douyin_state.json 登录态）。"""
    if not HAS_LOCAL:
        raise RuntimeError("scraper.py 不可用（缺 playwright 或 douyin_state.json）")
    with open_context("local") as ctx:
        return _scrape_local(ctx, keyword, max_videos)


def scrape_videos_firecrawl(keyword: str, max_videos: int) -> list[dict]:
    """Firecrawl 搜索页抓取（降级）。实测被抖音滑块验证码拦截，返回占位。"""
    from firecrawl import Firecrawl
    from config import DEFAULT_UA, FIRECRAWL_API_KEY, FIRECRAWL_API_URL
    from urllib.parse import quote

    if not FIRECRAWL_API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY 未配置")
    client = Firecrawl(api_key=FIRECRAWL_API_KEY, api_url=FIRECRAWL_API_URL)
    url = f"https://www.douyin.com/search/{quote(keyword)}?type=video"
    doc = client.scrape(
        url,
        formats=["links", "markdown"],
        actions=[
            {"type": "wait", "milliseconds": 2500},
            {"type": "scroll", "direction": "down"}, {"type": "wait", "milliseconds": 1200},
        ],
        headers={"User-Agent": DEFAULT_UA, "Cookie": DOUYIN_HOT_COOKIE},
        timeout=60000,
    )
    md = getattr(doc, "markdown", "") or ""
    if "验证码" in md or "请完成下列验证" in md:
        raise RuntimeError("Firecrawl 搜索页被抖音滑块验证码拦截")

    links = getattr(doc, "links", None) or []
    video_links = [str(l) for l in links if "/video/" in str(l)]
    # 解析 video_id 和标题（markdown 中 [标题](url) 对应）
    rows = []
    for u in video_links[:max_videos]:
        vid = u.rstrip("/").split("/")[-1].split("?")[0]
        rows.append({"video_id": vid, "title": "", "author": "", "url": u, "source": "firecrawl"})
    return rows


PROVIDERS = {"local": scrape_videos_local, "firecrawl": scrape_videos_firecrawl}


# ---- 主逻辑 ----

def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["keyword", "video_id", "title", "source"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _has_login_state() -> bool:
    """检查 douyin_state.json 是否含已登录标识（而非匿名会话 cookie）。"""
    path = Path(STATE_FILE)
    if not path.exists():
        return False
    try:
        import json as _json
        state = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    names = {c.get("name", "") for c in state.get("cookies", [])}
    return bool(names & set(LOGIN_COOKIE_MARKERS))


def run_round(
    provider: str,
    rounds: int = 1,
    top_n: int = 10,
    mode: str = "dry",
    fetch_hot: bool = True,
) -> list[dict]:
    """一轮采集：热榜 → 每词 top N 视频。返回所有视频行。"""
    out_dir = OUT_DIR / "collect"
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    hot_csv = out_dir / f"hot_{stamp}.csv"
    video_csv = out_dir / f"videos_{stamp}.csv"

    all_rows: list[dict] = []

    # 1) 热榜
    if fetch_hot:
        print("[*] 抓取热榜 ...")
        md = fetch_hot_markdown(rounds=rounds)
        hot = parse_hotlist(md)
        if hot:
            hot_csv = write_csv(hot, hot_csv)
            print(f"[+] 热榜 {len(hot)} 条 -> {hot_csv}")
        else:
            print("[!] 本轮热榜为空（可能被风控/页面未渲染），跳过写 CSV")
    else:
        hot = []
        print("[*] 跳过热榜（用现有 CSV）")

    # 2) 每词抓视频
    scraper = PROVIDERS.get(provider)
    if not scraper:
        raise RuntimeError(f"未知 provider: {provider}（可选 {list(PROVIDERS)}）")

    use_csv = hot if hot else _load_previous_hot()
    print(f"[*] {provider} 抓 {len(use_csv)} 个关键词 × top{top_n} 视频 (mode={mode})")

    if mode == "dry":
        # dry 模式不实际请求，只模拟行结构
        for item in use_csv:
            kw = item["title"]
            for i in range(min(top_n, 3)):  # dry 只造 3 行示意
                all_rows.append({
                    "keyword": kw,
                    "video_id": f"dry_{item['hot_id']}_{i+1}",
                    "title": f"<dry {kw} {i+1}>",
                    "author": "",
                    "url": f"https://www.douyin.com/video/dry_{i+1}",
                    "source": provider,
                    "rank": item.get("rank", ""),
                })
        print(f"[dry] 模拟 {len(use_csv)} 词 × top{top_n}（实际只写 top3 占位）")
    else:
        if provider == "local" and not _has_login_state():
            raise RuntimeError(
                "当前 douyin_state.json 不是已登录状态（不含 sessionid/odin_tt 等登录 "
                "cookie）。真实抓视频需要登录态：用 BitBrowser 打开抖音扫码登录后运行 "
                "python login_export.py --bit 导出。匿名 cookie 无法完成搜索视频抓取。"
            )
        first = True
        for idx, item in enumerate(use_csv, 1):
            kw = item["title"]
            print(f"[{idx}/{len(use_csv)}] 抓视频: {kw}")
            try:
                videos = scraper(kw, top_n)
            except Exception as e:
                msg = str(e)
                if "验证码" in msg or "滑块" in msg:
                    raise RuntimeError(f"搜索页被验证码拦截（{kw}）: {msg}") from e
                print(f"[!] {kw} 失败: {e}")
                videos = [{"video_id": f"err_{item['hot_id']}", "title": f"error: {e}",
                           "author": "", "url": "", "source": "error"}]
            if first:
                first = False
                if not videos or all(str(v.get("video_id", "")).startswith("err_") for v in videos):
                    raise RuntimeError(
                        f"首个关键词 '{kw}' 未抓到视频（0 条）。登录态可能无效、"
                        "cookie 已过期或页面被拦截。停止本轮，避免产出空数据。"
                    )
            for v in videos:
                v["keyword"] = kw
                v["rank"] = item.get("rank", "")
                v.setdefault("source", provider)
            all_rows.extend(videos)
            time.sleep(2)  # 防限流

    video_csv = write_csv(all_rows, video_csv)
    print(f"[+] 视频 {len(all_rows)} 行 -> {video_csv}")
    return all_rows


def _load_previous_hot() -> list[dict]:
    """从最近的热榜 CSV 读关键词（当本轮不抓热榜时）。"""
    hot_dir = OUT_DIR / "collect"
    if not hot_dir.exists():
        return []
    files = sorted(hot_dir.glob("hot_*.csv"), reverse=True)
    if not files:
        return []
    import csv as _csv
    with open(files[0], encoding="utf-8-sig") as f:
        return list(_csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description="抖音热榜→top10 视频 采集闭环（忽略 R2）")
    ap.add_argument("--provider", choices=list(PROVIDERS), default="local",
                    help="视频抓取方式（local=Playwright，firecrawl=当前被滑块拦截）")
    ap.add_argument("--rounds", type=int, default=1, help="热榜滚动轮数，默认 1")
    ap.add_argument("--top", type=int, default=10, help="每个关键词取前 N 个视频")
    ap.add_argument("--mode", choices=["dry", "real"], default="dry",
                    help="dry=只验证流水线不真实请求；real=真抓")
    ap.add_argument("--interval-min", type=int, default=65, help="循环间隔分钟")
    ap.add_argument("--loop", action="store_true", help="无限循环，每 interval-min 跑一轮")
    ap.add_argument("--skip-hot", action="store_true", help="本轮跳过抓热榜，用最近一份")
    args = ap.parse_args()

    if not args.loop:
        run_round(args.provider, args.rounds, args.top, args.mode, fetch_hot=not args.skip_hot)
        return

    # 无限循环：每 interval-min 分钟一轮
    print(f"[*] 循环模式：每 {args.interval_min} 分钟一轮")
    round_no = 0
    while True:
        round_no += 1
        print(f"\n===== 第 {round_no} 轮 @ {dt.datetime.now().isoformat(timespec='seconds')} =====")
        try:
            run_round(args.provider, args.rounds, args.top, args.mode, fetch_hot=not args.skip_hot)
        except Exception as e:
            print(f"[!] 本轮失败: {e}")
        print(f"[*] 等待 {args.interval_min} 分钟 ...")
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    main()