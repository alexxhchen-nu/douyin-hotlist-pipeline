"""对比 google_search True/False 两种会话下热榜 API 响应体的差异。"""
import asyncio
import json
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


async def run_once(tag: str, google_search: bool):
    cookies = load_env_cookies()

    async def setup(page):
        if cookies:
            try:
                await page.context.add_cookies(cookies)
            except Exception as e:
                print(f"{tag} cookie inject failed: {e}", flush=True)

    s = AsyncStealthySession(
        headless=True, network_idle=True, record_requests=True,
        max_pages=1, timeout=60000, wait=1500, google_search=google_search,
        page_setup=setup,
    )
    async with s:
        resp = await s.fetch(HOT_URL)
        doc = resp.body.decode("utf-8", errors="ignore")
        print(f"--- {tag} (google_search={google_search}) status={resp.status} doc={len(doc)}B", flush=True)
        hits = 0
        for r in s.network.search(resource_type="xhr", limit=None, include_static=False):
            if "hot/search/list" not in r.url:
                continue
            hits += 1
            ct = ""
            try:
                ct = r.headers.get("content-type", "")
            except Exception:
                pass
            body = r.body or b""
            print(f"  hot_api#{hits}: status={r.status} ct={ct!r} body={len(body)}B", flush=True)
            try:
                j = json.loads(body)
                d = j.get("data")
                print(f"    JSON ok, data type={type(d).__name__}", flush=True)
                if isinstance(d, dict):
                    print(f"    data keys: {list(d)[:12]}", flush=True)
                    for k, v in d.items():
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            print(f"    list@{k}: n={len(v)} first_keys={list(v[0])[:12]}", flush=True)
            except Exception as e:
                print(f"    json.loads FAILED: {type(e).__name__}: {e}", flush=True)
                print(f"    head: {body[:200]!r}", flush=True)


async def main():
    await run_once("referer-google", True)
    await run_once("referer-none", False)


asyncio.run(main())
