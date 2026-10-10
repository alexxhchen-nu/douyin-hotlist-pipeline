"""抖音热榜 → R2（Worker 边缘下载 + 20 并发）"""
import argparse, csv, datetime, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import PROVIDER, R2_BUCKET, R2_PREFIX
from downloader import list_keys, s3, upload_bytes, worker_download
from scraper import LoginRequired, current_ua, open_context, scrape_keyword

def read_keywords(csv_path, n):
    kws = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        col = None
        if reader.fieldnames:
            for name in reader.fieldnames:
                if name and any(s in name for s in ("关键词", "热词", "热搜")):
                    col = name; break
            col = col or reader.fieldnames[0]
        for row in reader:
            v = (row.get(col) or "").strip()
            if v: kws.append(v)
    return list(dict.fromkeys(kws))[-n:]  # 从末尾取 N 个

def slugify(kw):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", kw).strip("_")[:40]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="热榜 CSV 路径")
    ap.add_argument("--keywords", help="逗号分隔关键词")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--provider", choices=["local", "steel"], default=None)
    ap.add_argument("--workers", type=int, default=20, help="并发 Worker 下载")
    args = ap.parse_args()

    if args.csv:
        keywords = read_keywords(args.csv, args.n)
    elif args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()][:args.n]
    else:
        raise SystemExit("需要 --csv 或 --keywords")

    provider = args.provider or PROVIDER
    ua = current_ua()
    date = datetime.date.today().isoformat()
    client = s3()

    print(f"[*] 列出 R2 已有文件...")
    existing = list_keys(client, f"{R2_PREFIX}/{date}/")
    print(f"[*] 已有 {len(existing)} 个文件")

    rows = [("keyword", "video_id", "title", "r2_key", "status", "size_bytes")]
    print(f"[*] {provider} | {len(keywords)} 词 × ≤{args.max} 条 | {args.workers} 并发 Worker")

    with open_context(provider) as ctx:
        for kw in keywords:
            print(f"[*] 抓取: {kw}")
            try:
                videos = scrape_keyword(ctx, kw, args.max)
            except LoginRequired as e:
                print(f"[!] {e}"); break
            print(f"    解析 {len(videos)} 条 → Worker 下载...")

            ok = dup = fail = 0
            tasks = []
            for v in videos:
                key = f"{R2_PREFIX}/{date}/{slugify(kw)}/{v['video_id']}.mp4"
                if key in existing:
                    rows.append((kw, v["video_id"], v["title"], key, "duplicate", 0))
                    dup += 1; continue
                tasks.append((v, key))

            if tasks:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {
                        pool.submit(worker_download, v["play_url"], key, ua): (v, key)
                        for v, key in tasks
                    }
                    for fut in as_completed(futures):
                        v, key = futures[fut]
                        try:
                            size = fut.result()
                            rows.append((kw, v["video_id"], v["title"], key, "ok", size))
                            ok += 1
                        except Exception as e:
                            rows.append((kw, v["video_id"], v["title"], key, "failed", 0))
                            fail += 1
                            print(f"    [!] {v['video_id']}: {e}")

            print(f"[+] {kw}: 解析 {len(videos)} | 上传 {ok} | 重复 {dup} | 失败 {fail}")

    manifest = f"{R2_PREFIX}/manifest/{date}.csv"
    buf = []
    for row in rows:
        buf.append(",".join('"' + str(c).replace('"', '""') + '"' for c in row))
    upload_bytes(client, ("\r\n".join(buf)).encode("utf-8-sig"), manifest)
    print(f"[ok] manifest -> s3://{R2_BUCKET}/{manifest}")

if __name__ == "__main__":
    main()
