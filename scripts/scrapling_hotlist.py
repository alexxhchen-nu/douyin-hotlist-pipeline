"""抖音热榜抓取（Scrapling StealthyFetcher 版）：浏览器渲染 douyin.com/hot，输出 Top50 CSV。

与 scripts/hotlist.py（Firecrawl 版）字段对齐：
rank, title, hot_url, hot_id, hot_value_k, fetched_at

DOM 结构（2026-10 实测）：
  div.qe4SKjIp            — 榜单条目（51 个：0=置顶，1..50=Top50）
  div.OQtNjDJ9 > a > h3   — 标题
  a[href=/hot/<id>/slug]  — 条目链接
  div.m73YyvwD > span.ZZFBf5Wm — 热度值（单位：万/K/裸数字）
置顶项没有热度块（m73YyvwD），据此剔除，与 Firecrawl 版的 up.svg 过滤等价。
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from scrapling.fetchers import StealthyFetcher

class HotRow(TypedDict):
    rank: int
    title: str
    hot_url: str
    hot_id: str
    hot_value_k: Optional[float]
    fetched_at: str
HOT_URL = "https://www.douyin.com/hot"
ITEM_SEL = "div.qe4SKjIp"
TITLE_SEL = "div.OQtNjDJ9 a h3::text"
HEAT_SEL = "div.m73YyvwD span.ZZFBf5Wm::text"
HEAT_BLOCK_SEL = "div.m73YyvwD"

CSV_FIELDS = ["rank", "title", "hot_url", "hot_id", "hot_value_k", "fetched_at"]


def parse_heat(text: str) -> Optional[float]:
    """'1123.7万' -> 11237.0 (K 单位)；'1234.5K' -> 1234.5；裸数字原样。"""
    m = re.fullmatch(r"\s*([\d.]+)\s*(万|K|k)?\s*", text or "")
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        value *= 10  # 万 -> K
    return value


def fetch_hotlist(rounds: int = 1) -> list[HotRow]:
    # 抖音热榜是 SPA，浏览器渲染 + 等网络空闲
    page = StealthyFetcher.fetch(
        HOT_URL,
        network_idle=True,
        timeout=60000,
        wait=2000,
        retries=rounds,
    )
    rows: list[HotRow] = []
    for item in page.css(ITEM_SEL):
        # 置顶项无热度块，不属于 50 强
        if not item.css(HEAT_BLOCK_SEL):
            continue
        title = item.css(TITLE_SEL).get()
        href = item.css("a::attr(href)").get()
        heat_text = item.css(HEAT_SEL).get()
        hot_value_k = parse_heat(heat_text) if heat_text else None
        hot_url = page.urljoin(href) if href else ""
        hot_id = ""
        if href:
            m = re.search(r"/hot/(\d+)", href)
            hot_id = m.group(1) if m else ""
        rows.append(
            {
                "rank": len(rows) + 1,
                "title": (title or "").strip(),
                "hot_url": hot_url,
                "hot_id": hot_id,
                "hot_value_k": hot_value_k,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        if len(rows) >= 50:
            break
    return rows


def write_csv(rows: list[HotRow], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    ap = argparse.ArgumentParser(description="抖音热榜抓取（Scrapling 版）")
    ap.add_argument("-o", "--out", default="collect/hot_scrapling.csv", help="输出 CSV 路径")
    ap.add_argument("--rounds", type=int, default=1, help="失败重试次数")
    args = ap.parse_args()

    rows = fetch_hotlist(args.rounds)
    out = write_csv(rows, Path(args.out))
    print(f"写入 {out}，共 {len(rows)} 条")
    for r in rows[:5]:
        print(f"  #{r['rank']:>2} {r['title']}  ({r['hot_value_k']}K热度)")


if __name__ == "__main__":
    main()
