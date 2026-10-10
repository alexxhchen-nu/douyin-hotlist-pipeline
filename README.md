# 🎬 Douyin Hotlist Video Pipeline

> Automated daily collection of Douyin (TikTok China) trending videos — 50 keywords × up to 200 videos each — streamed directly to Cloudflare R2 via edge workers. Fully headless, zero local storage.

[简体中文](./README.zh-CN.md) | **English**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD50?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Workers+R2-F38020?logo=cloudflare&logoColor=white)](https://cloudflare.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Stars](https://img.shields.io/github/stars/alexxhchen-nu/douyin-hotlist-pipeline?style=social)](https://github.com/alexxhchen-nu/douyin-hotlist-pipeline)

---

<details>
<summary>📖 Table of Contents</summary>

- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [🚀 Quick Deploy](#-quick-deploy)
- [🔌 Multi-Platform Support](#-multi-platform-support)
- [🔑 How It Works](#-how-it-works)
- [📁 Project Structure](#-project-structure)
- [🛡️ Anti-Detection](#️-anti-detection)
- [📊 Output](#-output)
- [📈 Roadmap](#-roadmap)
- [⚠️ Disclaimer](#️-disclaimer)

</details>

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Scale** | 50 keywords × 200 videos = up to 10K videos/day (~100GB) |
| 🚀 **Speed** | 20 concurrent Worker downloads — zero local bandwidth |
| 🫥 **Stealth** | Headless Chromium with anti-detection flags + cookie injection from BitBrowser |
| 💾 **Zero Storage** | Videos stream from Douyin CDN → Cloudflare Edge → R2 directly |
| 🔄 **Dedup** | One-time R2 list at startup, O(1) in-memory lookup per video |
| 📦 **Manifest** | CSV with keyword, video_id, title, R2 key, status, size |
| ♻️ **Resumable** | Re-running skips already-downloaded videos automatically |
| 🔌 **Multi-Provider** | Steel.dev cloud browser switch with one flag |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL MACHINE (Windows)                       │
│                                                                  │
│  ┌────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │ 🪟 BitBrowser│────▶│ login_export │────▶│  🐍 main.py      │  │
│  │  (logged-in │ CDP│ .py --bit    │     │  (orchestrator)  │  │
│  │   US proxy)  │    │              │     │                  │  │
│  └────────────┘    │ cookie+UA    │     │  1. Read CSV     │  │
│                     │ export       │     │  2. List R2 keys │  │
│                     └──────┬───────┘     │  3. Dedup check   │  │
│                            │             └────────┬─────────┘  │
│                            ▼                      ▼            │
│                   ┌─────────────────┐   ┌──────────────────┐   │
│                   │ 📄 douyin_state  │   │ 🤖 Headless       │   │
│                   │ .json            │   │    Chromium       │   │
│                   │ 76 cookies + UA  │   │                   │   │
│                   └─────────────────┘   │ • Search keyword │   │
│                                         │ • Intercept API  │   │
│                                         │ • Extract URLs   │   │
│                                         │ • Scroll + dedup │   │
│                                         └────────┬──────────┘   │
│                                                  │ 20 POST      │
└──────────────────────────────────────────────────┼──────────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │    Cloudflare Edge Network     │
                                    │                                │
                                    │  ┌──────────────────────────┐ │
                                    │  │ ⚡ Worker: douyin-dl      │ │
                                    │  │ dl.xiaohanchen.cc         │ │
                                    │  │                           │ │
                                    │  │ POST {url, key, ua}      │ │
                                    │  │  → fetch(video_url)      │ │
                                    │  │  → R2.put(key, body)      │ │
                                    │  └────────────┬─────────────┘ │
                                    │               │               │
                                    │  ┌────────────▼─────────────┐ │
                                    │  │ 🪣 R2: pi-pipeline-test  │ │
                                    │  │                          │ │
                                    │  │ douyin-hotlist/          │ │
                                    │  │ ├── 2026-10-10/          │ │
                                    │  │ │   ├── keyword-1/       │ │
                                    │  │ │   │   ├── vid1.mp4     │ │
                                    │  │ │   │   └── ...          │ │
                                    │  │ │   └── keyword-2/       │ │
                                    │  │ └── manifest/            │ │
                                    │  │     └── 2026-10-10.csv   │ │
                                    │  └──────────────────────────┘ │
                                    └────────────────────────────────┘
```

## 🚀 Quick Deploy

### 📋 Prerequisites

| Requirement | Notes |
|---|---|
| 🐍 Python 3.10+ | Runtime environment |
| 🪟 BitBrowser (Windows) | Browser window with logged-in Douyin account |
| ☁️ Cloudflare account | R2 bucket + Workers enabled |
| 🟢 Node.js 18+ | Only needed for Worker deployment |

### Step 1: Clone & Install

```bash
git clone https://github.com/alexxhchen-nu/douyin-hotlist-pipeline.git
cd douyin-hotlist-pipeline

pip install -r requirements.txt
playwright install chromium
```

### Step 2: Configure

```bash
cp .env.example .env
# Edit .env with your R2 credentials, BitBrowser window ID, Worker URL
```

<details>
<summary>📄 .env Configuration (click to expand)</summary>

```ini
# ─── ☁️ R2 Configuration ───
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET=pi-pipeline-test
R2_PREFIX=douyin-hotlist

# ─── 🪟 BitBrowser ───
BIT_API=http://127.0.0.1:54345
BIT_WINDOW_ID=your_bitbrowser_window_id

# ─── 🌐 Steel.dev (optional, cloud browser) ───
STEEL_API_KEY=

# ─── ⚡ Cloudflare Worker ───
WORKER_URL=https://dl.yourdomain.com
```
</details>

### Step 3: Deploy Worker

```bash
cd worker/
npm install
npx wrangler deploy
cd ..
```

> ⚠️ **Cloudflare Zero Trust**: If your Worker returns a login page instead of JSON, delete the "All Workers" application in Zero Trust → Access → Applications.

### Step 4: Export Login State (one-time)

```bash
python login_export.py --bit
# 📥 Exports 76 cookies + UA from BitBrowser → douyin_state.json
```

### Step 5: Run

```bash
# 🧪 Test: 1 keyword × 5 videos
python main.py --keywords "NBA中国赛火箭战胜独行侠" --max 5

# 🚀 Full run: 50 keywords × 200 videos, 20 concurrent downloads
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 20
```

## 🔌 Multi-Platform Support

| Platform | Switch | Use Case | Status |
|---|---|---|---|
| 🖥️ **Local Chromium** | Default | Local Windows development, debugging | ✅ Primary |
| ☁️ **Steel.dev** | `--provider steel` | Cloud headless, large-scale concurrency | ✅ Built-in |
| 🪟 **BitBrowser** | `login_export.py --bit` | Login state production only | ✅ Built-in |
| 🔥 **Camoufox** | `scraper.py` StealthyFetcher | Linux server, high anti-detection | ⬜ Planned |
| 🌐 **Scrapling** | Parser layer overlay | Selector resilience, `find_similar()` | ⬜ Planned |
| ☁️ **Worker edge download** | Default | Zero local bandwidth, 20 concurrent | ✅ Primary |
| 💾 **Local boto3 streaming** | Replace `downloader.py` | Fallback when Worker is down | ✅ Built-in |

```bash
# ☁️ Steel.dev cloud mode
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 20 --provider steel

# 💾 Local download mode (no Worker)
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 8 --local
```

## 🔑 How It Works

### Cookie Flow

```
🪟 BitBrowser (logged-in) → CDP attach → storage_state() export
    ↓ 76 cookies + UA
📄 douyin_state.json
    ↓ inject
🤖 Headless Chromium → search → intercept API → extract URLs
    ↓ expiry detection
🚨 "扫码登录" (QR login) appears → re-export
```

### Douyin Search API

Video data is in `data[].aweme_info` (not `aweme_list` which is null):

```json
{
  "data": [{
    "aweme_info": {
      "aweme_id": "7694646195386815163",
      "desc": "#NBA 火箭VS独行侠中国赛",
      "video": {
        "play_addr": {
          "url_list": ["https://v.douyin.com/..."]
        }
      }
    }
  }]
}
```

### Worker Download Flow

```
🐍 main.py → POST {url, key, ua, referer} × 20 concurrent
    ↓
⚡ Worker (dl.xiaohanchen.cc)
    → fetch(video_url, {Referer, UA})
    → R2.put(key, body)
    → return {ok: true, key, size}
```

## 📁 Project Structure

```
douyin-hotlist-pipeline/
├── .env.example              # 🔧 Configuration template
├── .gitignore
├── requirements.txt         # 📦 Python dependencies
├── config.py                 # ⚙️ Unified config loader
├── login_export.py           # 🪟 BitBrowser → douyin_state.json
├── scraper.py                # 🤖 Headless Chromium: search → API intercept → extract URLs
├── downloader.py             # ⬇️ R2 upload + Worker edge download
├── main.py                   # 🐍 Orchestrator: CSV → scrape → 20 concurrent → manifest
├── worker/                   # ⚡ Cloudflare Worker source
│   ├── wrangler.toml         #    R2 binding + custom domain
│   └── src/index.js          #    POST handler: fetch → R2.put
├── docs/                     # 📚 Documentation
│   ├── pipeline-en.md        #    Architecture doc (English)
│   ├── pipeline-cn.md        #    Architecture doc (Chinese)
│   └── workflow.md           #    Operational workflow
└── LICENSE
```

## 🛡️ Anti-Detection

| # | Measure | Status |
|---|---|---|
| 1 | 🧢 UA matches BitBrowser window | ✅ |
| 2 | 🕐 Timezone/locale fixed (Asia/Shanghai, zh-CN) | ✅ |
| 3 | 🍪 76 cookies injected (including sessionid) | ✅ |
| 4 | 🫥 `--disable-blink-features=AutomationControlled` | ✅ |
| 5 | 🚫 `--enable-automation` flag removed | ✅ |
| 6 | 🚨 Login wall auto-detection | ✅ |
| 7 | 📦 Batch deduplication (no per-video HEAD) | ✅ |
| 8 | 😴 Random sleep jitter (5–15s) | ⬜ TODO |
| 9 | 🏠 Static residential proxy per identity | ⬜ TODO |
| 10 | 👥 Cookie/identity pool rotation | ⬜ TODO |

## 📊 Output

### R2 Storage Structure

```
pi-pipeline-test/douyin-hotlist/
├── 2026-10-10/
│   ├── NBA中国赛火箭战胜独行侠/
│   │   ├── 7694646195386815163.mp4
│   │   └── ... (up to 200 per keyword)
│   ├── 青岛海牛提前三轮降级/
│   │   └── ...
│   └── ... (50 keyword directories)
└── manifest/
    └── 2026-10-10.csv
```

### Manifest CSV

| keyword | video_id | title | r2_key | status | size_bytes |
|---|---|---|---|---|---|
| NBA中国赛 | 7694646195... | #NBA 火箭VS... | douyin-hotlist/...mp4 | ok | 15243890 |
| NBA中国赛 | 7694616254... | 独行侠vs火箭... | douyin-hotlist/...mp4 | duplicate | 0 |

## 📈 Roadmap

- [x] 🧪 **v1** — Local validation (1 keyword × 5 videos)
- [x] 🔍 **v2** — API response interception (`data[].aweme_info` parsing)
- [x] ⚡ **v3** — Cloudflare Worker edge download (20 concurrent)
- [x] 📦 **v4** — Batch R2 deduplication + manifest CSV
- [ ] 🚀 **v5** — Full 50 × 200 run validation (in progress)
- [ ] 🖥️ **v6** — SSH server deployment + cron + login expiry alerts
- [ ] 👥 **v7** — Identity pool (multiple BitBrowser windows + proxies + cookie rotation)
- [ ] 🌐 **v8** — Steel.dev for cloud scraping, expand to Kuaishou/Bilibili

## ⚠️ Disclaimer

This project is for research and educational purposes only. Please respect Douyin's Terms of Service and applicable laws in your jurisdiction. Use at your own risk.

---

<p align="center">
  <a href="./README.zh-CN.md">简体中文</a> · <a href="./README.md">English</a>
</p>
