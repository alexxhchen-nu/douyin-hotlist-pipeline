from pathlib import Path
from unittest import mock

import pytest

import firecrawl_scraper as fc


def test_cookie_header_missing_state(tmp_path):
    with mock.patch.object(fc, "DOUYIN_HOT_COOKIE", ""):
        fc.STATE_FILE = str(tmp_path / "missing.json")
        with pytest.raises(fc.FirecrawlAuthRequired, match="douyin_state.json 不存在"):
            fc.cookie_header()


def test_cookie_header_extracts_douyin_only(tmp_path):
    with mock.patch.object(fc, "DOUYIN_HOT_COOKIE", ""):
        fc.STATE_FILE = str(tmp_path / "state.json")
        (tmp_path / "state.json").write_text(
            '{"cookies":['
            '{"domain":".douyin.com","name":"sessionid","value":"abc"},'
            '{"domain":".example.com","name":"other","value":"x"}'
            "]}",
            encoding="utf-8",
        )
        assert fc.cookie_header() == "sessionid=abc"


def test_cookie_header_prefers_env_cookie(tmp_path):
    with mock.patch.object(fc, "DOUYIN_HOT_COOKIE", "ttwid=env_token"):
        fc.STATE_FILE = str(tmp_path / "state.json")
        (tmp_path / "state.json").write_text('{"cookies":[]}', encoding="utf-8")
        assert fc.cookie_header() == "ttwid=env_token"


def test_extract_videos_from_sdk_json():
    payload = {
        "videos": [
            {"video_id": "123", "title": "A", "author": "u1", "play_url": "//example.com/a.mp4", "detail_url": "https://www.douyin.com/video/123"},
            {"video_id": "456", "title": "B", "author": "u2", "play_url": "", "detail_url": "https://www.douyin.com/video/456"},
            {"title": "no id"},
        ]
    }
    videos = fc._extract_videos(payload)
    assert len(videos) == 2
    assert videos[0]["video_id"] == "123"
    assert videos[0]["play_url"] == "https://example.com/a.mp4"
    assert videos[1]["detail_url"].endswith("/456")


def test_scrape_requires_api_key():
    with mock.patch.object(fc, "FIRECRAWL_API_KEY", ""):
        with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
            fc._client()