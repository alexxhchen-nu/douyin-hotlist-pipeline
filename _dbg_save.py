"""探针：保存热榜页文档 + 全量 dump 记录的请求（xhr+fetch），定位热榜数据到底在哪。"""
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
        doc = resp.body.decode("utf-8", errors="ignore")
        Path("_hot_doc.html").write_text(doc, encoding="utf-8")
        print(f"status={resp.status} doc={len(doc)}B saved", flush=True)

        for rtype in ("xhr", "fetch"):
            recs = s.network.search(resource_type=rtype, limit=None, include_static=False)
            print(f"=== {rtype}: {len(recs)} records ===", flush=True)
            for r in recs:
                body = r.body or b""
                print(f"  {r.status} {r.url[:160]} body={len(body)}B", flush=True)


asyncio.run(main())
