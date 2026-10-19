"""探针：dump channel/hotspot 完整 URL + 保存响应体到本地。"""
import asyncio
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
        print(f"status={resp.status} doc={len(resp.body)}B", flush=True)
        n = 0
        for r in s.network.search(resource_type="xhr", limit=None, include_static=False):
            if "channel/hotspot" not in r.url:
                continue
            n += 1
            body = r.body or b""
            print(f"[{n}] {r.url}", flush=True)
            print(f"    status={r.status} body={len(body)}B head={body[:300]!r}", flush=True)
            Path(f"_hotspot_{n}.bin").write_bytes(body)
            try:
                import json
                j = json.loads(body)
                print(f"    JSON ok, top keys: {list(j)[:10]}", flush=True)
            except Exception as e:
                print(f"    not plain JSON: {type(e).__name__}", flush=True)


asyncio.run(main())
