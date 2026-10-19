"""抖音热榜抓取：Firecrawl + DOUYIN_HOT_COOKIE，只输出 CSV（忽略 R2）。

用法：
  python hotlist.py --out out/hotlist/hot_YYYY-MM-DD.csv [--rounds 4]

数据来源：抓取 douyin.com/hot 的 markdown，本地正则解析热榜区
（比 Firecrawl 的 LLM json 提取更完整、更便宜，不受 10 条截断限制）。
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import date, datetime
from pathlib import Path

from config import DEFAULT_UA, DOUYIN_HOT_COOKIE, FIRECRAWL_API_KEY, FIRECRAWL_API_URL

HOT_URL = "https://www.douyin.com/hot"

CSV_FIELDS = ["rank", "title", "hot_url", "hot_id", "hot_value_k", "fetched_at"]

# 条目形如: [**团结是战胜一切困难的强大力量**](https://www.douyin.com/hot/2703468/xxx)
ITEM_RE = re.compile(
    r"\[\*\*(?P<title>[^*]+)\*\*\]\(https?://www\.douyin\.com/hot/(?P<hot_id>\d+)[^)]*\)"
)
# 热度形如: 11103.5K热度
HOT_VALUE_RE = re.compile(r"([\d.]+)\s*K热度")
# 置顶位图标：位于榜单上方，带 up.svg 的条目不属于 50 强榜单
UP_ICON_RE = re.compile(r"icons/hot/up\.svg")


def _client():
    if not FIRECRAWL_API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY 未配置，请写入 .env")
    from firecrawl import Firecrawl

    return Firecrawl(api_key=FIRECRAWL_API_KEY, api_url=FIRECRAWL_API_URL)


def _scroll_actions(rounds: int) -> list[dict]:
    actions = [{"type": "wait", "milliseconds": 2500}]
    for _ in range(rounds):
        actions.append({"type": "scroll", "direction": "down"})
        actions.append({"type": "wait", "milliseconds": 1200})
    return actions


def fetch_hot_markdown(rounds: int = 4) -> str:
    """抓 douyin.com/hot，返回 markdown。"""
    if not DOUYIN_HOT_COOKIE:
        raise RuntimeError("DOUYIN_HOT_COOKIE 未配置：把 douyin.com 的 Cookie 串写入 .env")
    client = _client()
    doc = client.scrape(
        HOT_URL,
        formats=["markdown"],
        actions=_scroll_actions(rounds),
        headers={"User-Agent": DEFAULT_UA, "Cookie": DOUYIN_HOT_COOKIE},
        timeout=90000,
    )
    md = getattr(doc, "markdown", "") or ""
    if "# 抖音热榜" not in md:
        raise RuntimeError(f"Firecrawl 返回的 markdown 中没有热榜区（可能被验证码拦截）：{md[:200]}")
    return md


def parse_hotlist(md: str) -> list[dict]:
    """从热榜 markdown 区块提取条目。"""
    section = md.split("# 抖音热榜", 1)[1] if "# 抖音热榜" in md else md
    section = section.split("抖音热榜规则说明", 1)[0]

    items = list(ITEM_RE.finditer(section))
    if not items:
        return []

    values = list(HOT_VALUE_RE.finditer(section))

    rows = []
    prev_end = 0
    for idx, m in enumerate(items):
        title = m.group("title").strip()
        hot_id = m.group("hot_id")
        start = m.start()

        # 跳过置顶位：up.svg 紧跟在该条目之前（不与上一条重叠）
        between = section[prev_end:start]
        if UP_ICON_RE.search(between):
            prev_end = m.end()
            continue

        # 热度取该条目之后最近的一个
        value = ""
        for v in values:
            if v.start() > start:
                value = v.group(1)
                break

        # rank 直接用榜单内出现顺序：页面顺序即榜单排名，
        # 页面里的数字序号在前几名是图标时不可靠（会滞后错位）
        rows.append({
            "rank": len(rows) + 1,
            "title": title,
            "hot_url": f"https://www.douyin.com/hot/{hot_id}",
            "hot_id": hot_id,
            "hot_value_k": value,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        })
        prev_end = m.end()

    rows.sort(key=lambda r: r["rank"])
    # 去重（同一条可能因滚动重复出现）
    seen, dedup = set(), []
    for r in rows:
        if r["hot_id"] in seen:
            continue
        seen.add(r["hot_id"])
        dedup.append(r)
    return dedup


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    ap = argparse.ArgumentParser(description="抖音热榜抓取（Firecrawl markdown 解析，忽略 R2）")
    ap.add_argument("--out", default=f"out/hotlist/hot_{date.today().isoformat()}.csv")
    ap.add_argument("--rounds", type=int, default=4, help="向下滚动轮数，确保 50 条都加载")
    args = ap.parse_args()

    print(f"[*] 抓取 {HOT_URL} (滚动 {args.rounds} 轮) ...")
    md = fetch_hot_markdown(args.rounds)
    rows = parse_hotlist(md)
    print(f"[+] 解析到 {len(rows)} 条热榜")
    if not rows:
        raise SystemExit("无数据")

    out = write_csv(rows, Path(args.out))
    print(f"[ok] 已写入 {out}")
    for r in rows[:5]:
        print(f"  #{r['rank']:>2} {r['title']}  ({r['hot_value_k']}K热度)")


if __name__ == "__main__":
    main()