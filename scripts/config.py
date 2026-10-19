import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT") or (
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else "")
R2_BUCKET = os.environ.get("R2_BUCKET", "pi-pipeline-test")
R2_PREFIX = os.environ.get("R2_PREFIX", "douyin-hotlist")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")

BIT_API = os.environ.get("BIT_API", "http://127.0.0.1:54345")
BIT_WINDOW_ID = os.environ.get("BIT_WINDOW_ID", "")

STEEL_API_KEY = os.environ.get("STEEL_API_KEY", "")
STEEL_BASE = os.environ.get("STEEL_BASE_URL", "https://api.steel.dev")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_API_URL = os.environ.get("FIRECRAWL_API_URL", "https://api.firecrawl.dev")

# 直接用的 douyin.com/hot Cookie 串（分号分隔），优先于 douyin_state.json
DOUYIN_HOT_COOKIE = os.environ.get("DOUYIN_HOT_COOKIE", "")

WORKER_URL = os.environ.get("WORKER_URL", "https://dl.xiaohanchen.cc")

STATE_FILE = os.environ.get("STATE_FILE", str(ROOT / "douyin_state.json"))
PROFILE_DIR = os.environ.get("PROFILE_DIR", str(ROOT / "chrome_profile"))
PROVIDER = os.environ.get("PROVIDER", "local")
DEFAULT_UA = os.environ.get("DOUYIN_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
