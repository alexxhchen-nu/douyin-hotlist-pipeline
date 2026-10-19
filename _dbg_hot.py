"""探针：同款会话配置加载热榜页，dump 网络历史里每个 XHR 的 URL/状态/JSON 形状，确认 API 是否触发。"""
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


async def main():
    cookies = load_env_cookies()
    print(f"cookies loaded: {len(cookies)}", flush=True)

    async def setup(page):
        if cookies:
            try:
                await page.context.add_cookies(cookies)
                print("[cookies injected]", flush=True)
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
        print(f"status={resp.status} doc={len(doc)}B captcha_wall={'验证码中间页' in doc}", flush=True)

        for rtype in ("xhr", "fetch"):
            recs = s.network.search(resource_type=rtype, limit=None, include_static=False)
            print(f"--- {rtype} recorded: {len(recs)}", flush=True)
            for r in recs:
                j = None
                try:
                    j = r.json()
                except Exception:
                    pass
                print(f"  {r.status} {r.url[:130]} json={type(j).__name__ if j is not None else '-'}", flush=True)
                if isinstance(j, dict):
                    d = j.get("data")
                    if isinstance(d, dict):
                        print(f"     data dict keys: {list(d)[:10]}", flush=True)
                        for k, v in d.items():
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                print(f"     list@{k}: n={len(v)} first_keys={list(v[0])[:12]}", flush=True)
                    elif isinstance(d, list):
                        print(f"     data list n={len(d)}", flush=True)

        pushes = re.findall(r'self\.__pace_f\.push\(\[(\d+),\s*("(?:[^"\\]|\\.)*")\]\)', doc)
        print(f"RSC pushes in doc: {len(pushes)}", flush=True)
        if pushes:
            seg = json.loads(pushes[0][1])
            print(f"  sample seg head: {seg[:80]!r}", flush=True)


asyncio.run(main())
