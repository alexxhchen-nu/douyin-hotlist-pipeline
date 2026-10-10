"""导出抖音登录态：douyin_state.json（cookies + localStorage + UA）

用法：
  python login_export.py --bit   # 附加到已登录的比特浏览器窗口导出（推荐）
  python login_export.py --qr    # 本地开有头浏览器扫码后导出
"""
import argparse
import json
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from config import BIT_API, BIT_WINDOW_ID, STATE_FILE

OUT = Path(STATE_FILE)


def _save(state: dict):
    OUT.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    ua = state.get("ua", "")
    print(f"[ok] 已导出 {OUT}")
    print(f"[ok] UA: {ua}")
    print("[!] 该文件等于账号钥匙：不要进 git、不要外传")


def export_bit():
    r = requests.post(f"{BIT_API}/browser/open", json={"id": BIT_WINDOW_ID}, timeout=30)
    r.raise_for_status()
    ws = r.json()["data"]["ws"]
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws)
            ctx = browser.contexts[0]
            state = ctx.storage_state()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            state["ua"] = page.evaluate("navigator.userAgent")
        _save(state)
    finally:
        try:
            requests.post(f"{BIT_API}/browser/close", json={"id": BIT_WINDOW_ID}, timeout=30)
        except Exception:
            pass


def export_qr():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        page.goto("https://www.douyin.com/")
        input("手机扫码登录完成后，回车继续...")
        state = ctx.storage_state()
        state["ua"] = page.evaluate("navigator.userAgent")
        browser.close()
    _save(state)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bit", action="store_true", help=f"附加比特浏览器窗口 {BIT_WINDOW_ID}")
    g.add_argument("--qr", action="store_true", help="本地扫码登录")
    args = ap.parse_args()
    export_bit() if args.bit else export_qr()
