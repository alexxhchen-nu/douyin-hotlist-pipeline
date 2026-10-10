"""R2 上传 + Worker 边缘下载"""
import boto3, requests
from boto3.s3.transfer import TransferConfig
from config import (R2_ACCESS_KEY_ID, R2_BUCKET, R2_ENDPOINT,
                    R2_SECRET_ACCESS_KEY, WORKER_URL)

TRANSFER = TransferConfig(multipart_threshold=8*1024*1024, multipart_chunksize=8*1024*1024)

def s3():
    return boto3.client("s3", endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY, region_name="auto")

def list_keys(client, prefix):
    keys = set()
    token = None
    while True:
        kw = {"Bucket": R2_BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if token: kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for obj in resp.get("Contents", []): keys.add(obj["Key"])
        if not resp.get("IsTruncated"): break
        token = resp.get("NextContinuationToken")
    return keys

def worker_download(url, key, ua, referer="https://www.douyin.com/"):
    r = requests.post(WORKER_URL,
        json={"url": url, "key": key, "referer": referer, "ua": ua},
        timeout=(10, 300))
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(data.get("error", f"HTTP {r.status_code}"))
    return data.get("size", 0)

def upload_bytes(client, body, key, content_type="text/csv"):
    client.put_object(Bucket=R2_BUCKET, Key=key, Body=body, ContentType=content_type)
