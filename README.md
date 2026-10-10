# 🎬 Douyin Hotlist Video Pipeline

> Automated daily collection of Douyin (TikTok China) trending videos — 50 keywords × up to 200 videos each — streamed directly to Cloudflare R2 via edge workers. Fully headless, zero local storage.

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD50?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Cloudflare Workers](https://img.shields.io/badge/Cloudflare-Workers-F38020?logo=cloudflare&logoColor=white)](https://workers.cloudflare.com/)
[![R2](https://img.shields.io/badge/Storage-R2-F38020?logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/r2/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ Features

- **📊 Scale**: 50 trending keywords × 200 videos = up to 10,000 videos/day (~100GB/day)
- **🚀 Speed**: 20 concurrent Cloudflare Worker downloads — zero local bandwidth
- **🫥 Stealth**: Headless Chromium with anti-detection flags + cookie injection from BitBrowser
- **💾 Zero Local Storage**: Videos stream from Douyin CDN → Cloudflare Edge → R2 directly
- **🔄 Deduplication**: One-time R2 list at startup, O(1) in-memory lookup per video
- **📦 Manifest**: CSV with keyword, video_id, title, R2 key, status, size — uploaded to R2
- **🔄 Resumable**: Re-running skips already-downloaded videos automatically

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL MACHINE (Windows)                       │
│                                                                  │
│  ┌────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │ BitBrowser  │────▶│ login_export │────▶│  main.py         │  │
│  │ (logged-in, │ CDP │ .py --bit    │     │  (orchestrator)  │  │
│  │  US proxy)  │     │              │     │                  │  │
│  └────────────┘     │ storage_state│     │  1. Read CSV     │  │
│                      │ + UA export  │     │  2. List R2 keys │  │
│                      └──────┬───────┘     │  3. Dedup check  │  │
│                             │             └────────┬─────────┘  │
│                             ▼                      ▼            │
│                   ┌─────────────────┐   ┌──────────────────┐   │
│                   │ douyin_state     │   │ Headless Chromium │   │
│                   │ .json            │   │ (Playwright)     │   │
│                   │ 76 cookies + UA  │   │                  │   │
│                   └─────────────────┘   │ • Search keyword │   │
│                                         │ • Intercept API  │   │
│                                         │ • Extract URLs   │   │
│                                         │ • Scroll + dedup │   │
│                                         └────────┬─────────┘   │
│                                                  │ 20 POST      │
└──────────────────────────────────────────────────┼──────────────┘
                                                   │
                                   ┌───────────────┼──────────────┐
                                   │    Cloudflare Edge Network     │
                                   │                                │
                                   │  ┌──────────────────────────┐ │
                                   │  │ Worker: douyin-dl         │ │
                                   │  │ dl.xiaohanchen.cc         │ │
                                   │  │                           │ │
                                   │  │ POST {url, key, ua}      │ │
                                   │  │   → fetch(video_url)      │ │
                                   │  │   → R2.put(key, body)      │ │
                                   │  └────────────┬─────────────┘ │
                                   │               │               │
                                   │  ┌────────────▼─────────────┐ │
                                   │  │ R2: pi-pipeline-test     │ │
                                   │  │                          │ │
                                   │  │ douyin-hotlist/          │ │
                                   │  │ ├── 2026-10-10/          │ │
                                   │  │ │   ├── keyword-1/       │ │
                                   │  │ │   │   ├── vid1.mp4    │ │
                                   │  │ │   │   └── ...         │ │
                                   │  │ │   └── keyword-2/       │ │
                                   │  │ └── manifest/            │ │
                                   │  │     └── 2026-10-10.csv  │ │
                                   │  └──────────────────────────┘ │
                                   └────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **BitBrowser** (Windows) with a logged-in Douyin account
- **Cloudflare account** with R2 bucket + Workers enabled
- **Node.js 18+** (for Worker deployment only)

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/douyin-hotlist-pipeline.git
cd douyin-hotlist-pipeline

pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your R2 credentials, BitBrowser window ID, Worker URL
```

See [.env.example](.env.example) for all required variables.

### 3. Deploy the Worker

```bash
cd worker/
npm install
npx wrangler deploy
cd ..
```

> **⚠️ Cloudflare Zero Trust**: If your Worker returns a login page instead of JSON, delete the "All Workers" application in Zero Trust → Access → Applications.

### 4. Export Login State (one-time)

```bash
python login_export.py --bit
# Attaches to BitBrowser via CDP → exports 76 cookies + UA to douyin_state.json
```

### 5. Run

```bash
# Test: 1 keyword × 5 videos
python main.py --keywords "NBA中国赛火箭战胜独行侠" --max 5

# Full run: 50 keywords × 200 videos, 20 concurrent downloads
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 20
```

---

## 📁 Project Structure

```
douyin-hotlist-pipeline/
├── .env.example                    # Configuration template
├── .gitignore
├── requirements.txt               # Python dependencies
├── config.py                       # Unified config loader
├── login_export.py                 # BitBrowser CDP → douyin_state.json
├── scraper.py                      # Headless Chromium: search → API intercept → extract URLs
├── downloader.py                    # R2 upload + Worker edge download
├── main.py                         # Orchestrator: CSV → scrape → 20-concurrent → manifest
├── worker/                         # Cloudflare Worker source
│   ├── wrangler.toml               # R2 binding + custom domain
│   └── src/
│       └── index.js                # POST handler: fetch → R2.put
└── docs/
    ├── pipeline-en.md              # Architecture doc (English)
    ├── pipeline-cn.md              # Architecture doc (Chinese)
    └── workflow.md                 # Operational workflow with diagrams
```

---

## 🔑 How It Works

### Cookie Flow

1. **Export**: Attach to BitBrowser's logged-in window via CDP → `storage_state()` exports cookies + UA
2. **Inject**: Launch headless Chromium → inject 76 cookies → warm up `douyin.com`
3. **Detect**: If search page shows "扫码登录" (QR login) → cookies expired → re-export

### Douyin Search API

The scraper intercepts `/aweme/v1/web/search/item/` API responses. Video data is in `data[].aweme_info` (not `aweme_list` which is null):

```json
{
  "data": [
    {
      "aweme_info": {
        "aweme_id": "7694646195386815163",
        "desc": "#NBA 火箭VS独行侠中国赛",
        "video": {
          "play_addr": {
            "url_list": ["https://v.douyin.com/..."]
          }
        }
      }
    }
  ]
}
```

### Worker Download

```
main.py → POST {url, key, ua, referer} → Worker
Worker → fetch(video_url, {Referer, UA}) → R2.put(key, body)
Worker → return {ok: true, key, size}
```

20 concurrent threads, zero local bandwidth.

---

## 🛡️ Anti-Detection

| Measure | Status |
|---|---|
| User-Agent matches BitBrowser | ✅ |
| Timezone/locale fixed (Asia/Shanghai, zh-CN) | ✅ |
| 76 cookies injected (including sessionid) | ✅ |
| `--disable-blink-features=AutomationControlled` | ✅ |
| `--enable-automation` flag removed | ✅ |
| Login wall auto-detection | ✅ |
| Batch deduplication (no per-video HEAD) | ✅ |
| Random sleep jitter (5–15s) | ⬜ TODO |
| Static residential proxy per identity | ⬜ TODO |

---

## 📊 Output

### R2 Structure

```
pi-pipeline-test/douyin-hotlist/
├── 2026-10-10/
│   ├── NBA中国赛火箭战胜独行侠/
│   │   ├── 7694646195386815163.mp4
│   │   └── ... (up to 200)
│   └── manifest/
│       └── 2026-10-10.csv
```

### Manifest CSV

| keyword | video_id | title | r2_key | status | size_bytes |
|---|---|---|---|---|---|
| NBA中国赛 | 7694646195... | #NBA 火箭VS... | douyin-hotlist/2026-10-10/NBA.../7694...mp4 | ok | 15243890 |

---

## 🔄 Alternative Providers

| Provider | Switch | Notes |
|---|---|---|
| **Steel.dev** (cloud browser) | `--provider steel` | Add `STEEL_API_KEY` to `.env`. No local browser needed. |
| **Local boto3 streaming** | Replace `worker_download` with `download_to_r2` | Uses local bandwidth. Fallback when Worker is down. |
| **BitBrowser for scraping** | Not implemented | Only used for login state production. |

---

## 📈 Roadmap

- [x] v1 — Local validation (1 keyword × 5 videos)
- [x] v2 — API response interception (`data[].aweme_info` parsing)
- [x] v3 — Cloudflare Worker edge download (20 concurrent)
- [x] v4 — Batch R2 deduplication + manifest CSV
- [ ] v5 — Full 50 × 200 run validation
- [ ] v6 — SSH server deployment + cron + login expiry alerts
- [ ] v7 — Identity pool (multiple BitBrowser windows + proxies)
- [ ] v8 — Steel.dev for cloud scraping, expand to other platforms

---

## 📝 License

[MIT](LICENSE) — This project is for research and educational purposes. Please respect Douyin's Terms of Service and applicable laws in your jurisdiction.
