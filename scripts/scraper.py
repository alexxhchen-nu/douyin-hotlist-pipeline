"""无头抓取：搜索页 API 拦截"""
import json
from contextlib import contextmanager
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
from config import DEFAULT_UA, PROFILE_DIR, STATE_FILE, STEEL_API_KEY, STEEL_BASE

SEARCH_URL = "https://www.douyin.com/search/{kw}?type=video"

class LoginRequired(RuntimeError): pass

def load_state():
    return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))

def current_ua():
    return load_state().get("ua") or DEFAULT_UA

def _seed_cookies(ctx, state):
    ctx.add_cookies(state.get("cookies", []))
    origin = next((o for o in state.get("origins", [])
                   if "douyin.com" in o.get("origin", "")), None)
    if not origin: return
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
        for kv in origin.get("localStorage", []):
            try: page.evaluate("[k,v]=>localStorage.setItem(k,v)", [kv["name"], kv["value"]])
            except: pass
        page.close()
    except: pass

def _parse_aweme(aw):
    if not isinstance(aw, dict): return None
    vid = str(aw.get("aweme_id", ""))
    if not vid: return None
    video = aw.get("video", {})
    if not isinstance(video, dict): return None
    pa = video.get("play_addr", {})
    if not isinstance(pa, dict): return None
    urls = pa.get("url_list") or []
    if not urls: return None
    url = urls[0]
    if url.startswith("//"): url = "https:" + url
    title = aw.get("desc", "") or ""
    au = aw.get("author", {})
    author = au.get("nickname", "") if isinstance(au, dict) else ""
    return {"video_id": vid, "title": title, "author": author, "play_url": url}

def _extract_awemes(data):
    if not isinstance(data, dict): return []
    results = []
    awemes = data.get("aweme_list")
    if isinstance(awemes, list):
        for aw in awemes:
            r = _parse_aweme(aw)
            if r: results.append(r)
    data_list = data.get("data")
    if isinstance(data_list, list):
        for item in data_list:
            if isinstance(item, dict):
                aw = item.get("aweme_info")
                if isinstance(aw, dict):
                    r = _parse_aweme(aw)
                    if r: results.append(r)
    return results

@contextmanager
def open_context(provider):
    state = load_state()
    ua = current_ua()
    with sync_playwright() as p:
        if provider == "steel":
            key = STEEL_API_KEY
            if not key: raise RuntimeError("STEEL_API_KEY 未配置")
            r = requests.post(f"{STEEL_BASE}/v1/sessions",
                headers={"steel-api-key": key}, json={}, timeout=60)
            r.raise_for_status()
            session = r.json()
            ws = session["websocketUrl"]
            sep = "&" if "?" in ws else "?"
            browser = p.chromium.connect_over_cdp(f"{ws}{sep}apiKey={key}")
            try:
                ctx = browser.contexts[0]
                _seed_cookies(ctx, state)
                yield ctx
            finally:
                try: requests.delete(f"{STEEL_BASE}/v1/sessions/{session['id']}",
                    headers={"steel-api-key": key}, timeout=30)
                except: pass
        else:
            ctx = p.chromium.launch_persistent_context(
                PROFILE_DIR, headless=True, user_agent=ua,
                locale="zh-CN", timezone_id="Asia/Shanghai",
                viewport={"width": 1600, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"])
            try:
                _seed_cookies(ctx, state)
                yield ctx
            finally: ctx.close()

def scrape_keyword(ctx, keyword, max_videos):
    page = ctx.new_page()
    collected = {}
    def on_response(resp):
        try:
            if "search/item" not in resp.url: return
            data = resp.json()
            for aw in _extract_awemes(data):
                collected.setdefault(aw["video_id"], aw)
        except: pass
    page.on("response", on_response)
    try:
        page.goto(SEARCH_URL.format(kw=keyword), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        if page.get_by_text("扫码登录").count():
            raise LoginRequired(f"[{keyword}] 登录墙")
        no_growth = 0
        while len(collected) < max_videos and no_growth < 4:
            before = len(collected)
            for _ in range(2):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(500)
            if len(collected) == before: no_growth += 1
            else: no_growth = 0
    finally: page.close()
    return list(collected.values())[:max_videos]
