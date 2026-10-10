# 🎬 Douyin Hotlist Video Pipeline

> Automated daily collection of Douyin (TikTok China) trending videos — 50 keywords × up to 200 videos each — streamed directly to Cloudflare R2 via edge workers. Fully headless, zero local storage.

**简体中文** | [English](./README.md)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD50?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Workers+R2-F38020?logo=cloudflare&logoColor=white)](https://cloudflare.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Stars](https://img.shields.io/github/stars/alexxhchen-nu/douyin-hotlist-pipeline?style=social)](https://github.com/alexxhchen-nu/douyin-hotlist-pipeline)

---

<details>
<summary>📖 目录</summary>

- [✨ 特性](#-特性)
- [🏗️ 架构](#️-架构)
- [🚀 一键部署](#-一键部署)
- [🔌 多平台支持](#-多平台支持)
- [🔑 工作原理](#-工作原理)
- [📁 项目结构](#-项目结构)
- [🛡️ 反风控措施](#️-反风控措施)
- [📊 输出](#-输出)
- [📈 路线图](#-路线图)
- [⚠️ 免责声明](#️-免责声明)

</details>

## ✨ 特性

| 特性 | 说明 |
|---|---|
| 📊 **规模** | 50 词 × 200 条 = 每日最多 10,000 条视频（~100GB） |
| 🚀 **速度** | 20 并发 Worker 下载，零本地带宽 |
| 🫥 **隐身** | 无头 Chromium + 反检测标志 + BitBrowser Cookie 注入 |
| 💾 **零存储** | 视频从抖音 CDN → Cloudflare 边缘 → R2，不碰本地磁盘 |
| 🔄 **去重** | 启动时一次性列出 R2 全量 key，O(1) 内存查找 |
| 📦 **清单** | CSV 含关键词、视频 ID、标题、R2 路径、状态、大小 |
| ♻️ **可恢复** | 中断后重跑自动跳过已下载视频 |
| 🔌 **多平台** | 支持 Steel.dev 云端浏览器一键切换 |

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    🖥️ 本地机器 (Windows)                          │
│                                                                  │
│  ┌────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │ 🪟 BitBrowser│────▶│ login_export │────▶│  🐍 main.py      │  │
│  │  (已登录窗口 │ CDP│ .py --bit    │     │  (调度器)         │  │
│  │   美国代理)  │    │              │     │                  │  │
│  └────────────┘    │ cookie+UA    │     │  1. 读热榜 CSV    │  │
│                     │ 导出         │     │  2. 列 R2 已有key │  │
│                     └──────┬───────┘     │  3. 去重检查      │  │
│                            │             └────────┬─────────┘  │
│                            ▼                      ▼            │
│                   ┌─────────────────┐   ┌──────────────────┐   │
│                   │ 📄 douyin_state  │   │ 🤖 Headless       │   │
│                   │ .json            │   │    Chromium       │   │
│                   │ 76 cookies + UA  │   │                   │   │
│                   └─────────────────┘   │ • 搜索关键词       │   │
│                                         │ • 拦截 API 响应    │   │
│                                         │ • 提取签名直链     │   │
│                                         │ • 滚动 + 去重      │   │
│                                         └────────┬──────────┘   │
│                                                  │ 20 并发 POST   │
└──────────────────────────────────────────────────┼───────────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │  ☁️ Cloudflare 边缘网络        │
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

## 🚀 一键部署

### 📋 前置条件

| 条件 | 说明 |
|---|---|
| 🐍 Python 3.10+ | 本地运行环境 |
| 🪟 BitBrowser (Windows) | 已登录抖音账号的浏览器窗口 |
| ☁️ Cloudflare 账号 | R2 桶 + Workers 已启用 |
| 🟢 Node.js 18+ | 仅部署 Worker 时需要 |

### 第一步：克隆 & 安装

```bash
git clone https://github.com/alexxhchen-nu/douyin-hotlist-pipeline.git
cd douyin-hotlist-pipeline

pip install -r requirements.txt
playwright install chromium
```

### 第二步：配置

```bash
cp .env.example .env
# 编辑 .env，填入 R2 密钥、BitBrowser 窗口 ID、Worker URL
```

<details>
<summary>📄 .env 配置项说明（点击展开）</summary>

```ini
# ─── ☁️ R2 配置 ───
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET=pi-pipeline-test
R2_PREFIX=douyin-hotlist

# ─── 🪟 比特浏览器 ───
BIT_API=http://127.0.0.1:54345
BIT_WINDOW_ID=your_bitbrowser_window_id

# ─── 🌐 Steel.dev（可选，云端浏览器） ───
STEEL_API_KEY=

# ─── ⚡ Cloudflare Worker ───
WORKER_URL=https://dl.yourdomain.com
```
</details>

### 第三步：部署 Worker

```bash
cd worker/
npm install
npx wrangler deploy
cd ..
```

> ⚠️ **Cloudflare Zero Trust**: 如果 Worker 返回登录页而非 JSON，去 Zero Trust → Access → Applications 删除 "All Workers" 应用。

### 第四步：导出登录态

```bash
python login_export.py --bit
# 📥 从 BitBrowser 窗口导出 76 条 Cookie + UA → douyin_state.json
```

### 第五步：运行

```bash
# 🧪 测试：1 个关键词 × 5 条视频
python main.py --keywords "NBA中国赛火箭战胜独行侠" --max 5

# 🚀 全量：50 个关键词 × 200 条视频，20 并发下载
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 20
```

## 🔌 多平台支持

| 平台 | 切换方式 | 适用场景 | 状态 |
|---|---|---|---|
| 🖥️ **本地 Chromium** | 默认 | 本地 Windows 开发、调试 | ✅ 主力 |
| ☁️ **Steel.dev** | `--provider steel` | 云端无头、大规模并发 | ✅ 已内置 |
| 🪟 **BitBrowser** | `login_export.py --bit` | 仅用于登录态生产 | ✅ 已内置 |
| 🔥 **Camoufox** | `scraper.py` StealthyFetcher | Linux 服务器、反检测 | ⬜ 规划中 |
| 🌐 **Scrapling** | 解析层叠加 | 选择器抗改版 | ⬜ 规划中 |
| ☁️ **Worker 边缘下载** | 默认 | 零本地带宽、20 并发 | ✅ 主力 |
| 💾 **本地 boto3 流式** | 替换 `downloader.py` | Worker 不可用兜底 | ✅ 已内置 |

```bash
# ☁️ Steel.dev 云端模式
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 20 --provider steel

# 💾 本地下载模式（不用 Worker）
python main.py --csv "hotlist.csv" --n 50 --max 200 --workers 8 --local
```

## 🔑 工作原理

### Cookie 流程

```
🪟 BitBrowser（已登录） → CDP 附加 → storage_state() 导出
    ↓ 76 条 Cookie + UA
📄 douyin_state.json
    ↓ 注入
🤖 Headless Chromium → 搜索 → 拦截 API → 提取直链
    ↓ 失效检测
🚨 "扫码登录"出现 → 重新导出
```

### 抖音搜索 API

视频数据在 `data[].aweme_info`（不是 `aweme_list`，那个是 null）：

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

### Worker 下载流程

```
🐍 main.py → POST {url, key, ua, referer} × 20 并发
    ↓
⚡ Worker (dl.xiaohanchen.cc)
    → fetch(video_url, {Referer, UA})
    → R2.put(key, body)
    → return {ok: true, key, size}
```

## 📁 项目结构

```
douyin-hotlist-pipeline/
├── .env.example              # 🔧 配置模板
├── .gitignore
├── requirements.txt         # 📦 Python 依赖
├── config.py                 # ⚙️ 统一配置读取
├── login_export.py           # 🪟 BitBrowser → douyin_state.json
├── scraper.py                # 🤖 无头 Chromium：搜索 → API 拦截 → 提取直链
├── downloader.py             # ⬇️ R2 上传 + Worker 边缘下载
├── main.py                   # 🐍 调度入口：CSV → 抓取 → 20 并发 → manifest
├── worker/                   # ⚡ Cloudflare Worker 源码
│   ├── wrangler.toml         #    R2 绑定 + 自定义域名
│   └── src/index.js          #    POST 处理：fetch → R2.put
├── docs/                     # 📚 文档
│   ├── pipeline-en.md        #    架构文档（英文）
│   ├── pipeline-cn.md        #    架构文档（中文）
│   └── workflow.md           #    工作流程图
└── LICENSE
```

## 🛡️ 反风控措施

| # | 措施 | 状态 |
|---|---|---|
| 1 | 🧢 UA 与 BitBrowser 窗口一致 | ✅ |
| 2 | 🕐 时区/语言恒定 (Asia/Shanghai, zh-CN) | ✅ |
| 3 | 🍪 76 条 Cookie 注入（含 sessionid） | ✅ |
| 4 | 🫥 `--disable-blink-features=AutomationControlled` | ✅ |
| 5 | 🚫 移除 `--enable-automation` 标志 | ✅ |
| 6 | 🚨 登录墙自动检测 | ✅ |
| 7 | 📦 批量去重（避免逐条 HEAD） | ✅ |
| 8 | 😴 请求间随机 sleep（5–15s 抖动） | ⬜ TODO |
| 9 | 🏠 每身份绑定静态住宅代理 | ⬜ TODO |
| 10 | 👥 Cookie/身份池轮换 | ⬜ TODO |

## 📊 输出

### R2 存储结构

```
pi-pipeline-test/douyin-hotlist/
├── 2026-10-10/
│   ├── NBA中国赛火箭战胜独行侠/
│   │   ├── 7694646195386815163.mp4
│   │   └── ... (每词最多 200 条)
│   ├── 青岛海牛提前三轮降级/
│   │   └── ...
│   └── ... (50 个关键词目录)
└── manifest/
    └── 2026-10-10.csv
```

### Manifest CSV

| keyword | video_id | title | r2_key | status | size_bytes |
|---|---|---|---|---|---|
| NBA中国赛 | 7694646195... | #NBA 火箭VS... | douyin-hotlist/...mp4 | ok | 15243890 |
| NBA中国赛 | 7694616254... | 独行侠vs火箭... | douyin-hotlist/...mp4 | duplicate | 0 |

## 📈 路线图

- [x] 🧪 **v1** — 本地验证（1 词 × 5 条）
- [x] 🔍 **v2** — API 响应拦截（`data[].aweme_info` 解析）
- [x] ⚡ **v3** — Cloudflare Worker 边缘下载（20 并发）
- [x] 📦 **v4** — 批量 R2 去重 + manifest CSV
- [ ] 🚀 **v5** — 全量 50 × 200 验证（进行中）
- [ ] 🖥️ **v6** — SSH 服务器部署 + cron 定时 + 登录过期告警
- [ ] 👥 **v7** — 身份池（多 BitBrowser 窗口 + 静态住宅代理 + Cookie 轮换）
- [ ] 🌐 **v8** — Steel.dev 接管云端抓取，扩展到快手/B站

## ⚠️ 免责声明

本项目仅供研究和教育目的。请遵守抖音的服务条款和所在地区的法律法规。使用者自行承担风险。
