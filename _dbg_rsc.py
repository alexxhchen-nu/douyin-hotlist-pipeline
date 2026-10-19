"""探针：从热榜页文档的 RSC flight 段里挖热榜条目，验证 RSC 兜底解析可行。"""
import asyncio
import json
import re
from pathlib import Path

from scrapling.fetchers import AsyncStealthySession

HOT_URL = "https://www.douyin.com/hot"


def load_env_cookies() -> list[dict]:
    env_path = Path(".env")
    if not env_path.exists():
        return []
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    raw = env.get("DOUYIN_HOT_COOKIE", "")
    out = []
    for p in raw.split(";"):
        if "=" in p:
            n, v = p.split("=", 1)
            n, v = n.strip(), v.strip()
            if n and v:
                out.append({"name": n, "value": v, "domain": ".douyin.com", "path": "/"})
    return out


def walk(obj, out):
    if isinstance(obj, dict):
        if isinstance(obj.get("word"), str) and ("hot_value" in obj or "view_count" in obj):
            out.append(obj)
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def rsc_hot_entries(doc: str):
    found = []
    for m in re.finditer(r'self\.__pace_f\.push\(\[(\d+),\s*("(?:[^"\\]|\\.)*")\]\)', doc):
        try:
            seg = json.loads(m.group(2))
        except Exception:
            continue
        if not isinstance(seg, str):
            continue
        start = min(i for i in (seg.find("{"), seg.find("[")) if i != -1) if ("{" in seg or "[" in seg) else -1
        if start == -1:
            continue
        try:
            data = json.loads(seg[start:])
        except Exception:
            continue
        walk(data, found)
    seen, out = set(), []
    for d in found:
        key = d.get("word")
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


async def main():
    cookies = load_env_cookies()

    async def setup(page):
        if cookies:
            try:
                await page.context.add_cookies(cookies)
            except Exception as e:
                print("cookie inject failed:", e, flush=True)

    s = AsyncStealthySession(
        headless=True, network_idle=True, record_requests=True,
        max_pages=1, timeout=60000, wait=1500, google_search=False,
        page_setup=setup,
    )
    async with s:
        resp = await s.fetch(HOT_URL)
        doc = resp.body.decode("utf-8", errors="ignore")
        print(f"status={resp.status} doc={len(doc)}B", flush=True)
        pushes = re.findall(r'self\.__pace_f\.push\(\[(\d+),\s*("(?:[^"\\]|\\.)*")\]\)', doc)
        print(f"RSC pushes: {len(pushes)}", flush=True)
        entries = rsc_hot_entries(doc)
        print(f"RSC hot entries found: {len(entries)}", flush=True)
        for e in entries[:5]:
            print(
                "  " + json.dumps(
                    {k: e.get(k) for k in ("word", "hot_value", "view_count", "position", "rank", "label", "word_type") if k in e},
                    ensure_ascii=False,
                ),
                flush=True,
            )


asyncio.run(main())
