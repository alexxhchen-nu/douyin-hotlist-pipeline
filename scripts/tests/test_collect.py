from pathlib import Path
from unittest import mock

import pytest

import collect


def _hot_rows(n=3):
    return [
        {"rank": i, "title": f"关键词{i}", "hot_url": f"https://www.douyin.com/hot/{i}",
         "hot_id": str(i), "hot_value_k": "1.0", "fetched_at": "t"}
        for i in range(1, n + 1)
    ]


def test_run_round_dry_produces_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT_DIR", tmp_path)
    monkeypatch.setattr(collect, "fetch_hot_markdown", lambda rounds=1: "# 抖音热榜\n")
    monkeypatch.setattr(collect, "parse_hotlist", lambda md: _hot_rows(3))
    rows = collect.run_round("local", rounds=1, top_n=10, mode="dry")
    assert len(rows) == 3 * 3  # 每个 hot 词 dry 只造 3 行
    out = list((tmp_path / "collect").glob("videos_*.csv"))
    assert out, "videos CSV should exist"
    text = out[0].read_text(encoding="utf-8-sig")
    assert "keyword" in text and "关键词1" in text


def _login_state(tmp_path):
    (tmp_path / "state.json").write_text(
        '{"cookies":[{"name":"sessionid","value":"abc123","domain":".douyin.com"}]}',
        encoding="utf-8",
    )


def test_real_mode_requires_login_state(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT_DIR", tmp_path)
    monkeypatch.setattr(collect, "fetch_hot_markdown", lambda rounds=1: "# 抖音热榜\n")
    monkeypatch.setattr(collect, "parse_hotlist", lambda md: _hot_rows(1))
    monkeypatch.setattr(collect, "STATE_FILE", str(tmp_path / "missing_state.json"))
    with pytest.raises(RuntimeError, match="不是已登录状态"):
        collect.run_round("local", rounds=1, top_n=10, mode="real")


def test_unknown_provider_rejected(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="未知 provider"):
        collect.run_round("nope", mode="dry")


def test_verify_suspends_on_captcha(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT_DIR", tmp_path)
    monkeypatch.setattr(collect, "fetch_hot_markdown", lambda rounds=1: "# 抖音热榜\n")
    monkeypatch.setattr(collect, "parse_hotlist", lambda md: _hot_rows(1))
    monkeypatch.setattr(collect, "STATE_FILE", str(tmp_path / "state.json"))
    _login_state(tmp_path)
    monkeypatch.setattr(
        collect, "PROVIDERS",
        {"local": lambda kw, n: (_ for _ in ()).throw(RuntimeError("被滑块验证码拦截"))},
    )
    with pytest.raises(RuntimeError, match="验证码"):
        collect.run_round("local", rounds=1, top_n=10, mode="real")


def test_first_keyword_empty_aborts(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT_DIR", tmp_path)
    monkeypatch.setattr(collect, "fetch_hot_markdown", lambda rounds=1: "# 抖音热榜\n")
    monkeypatch.setattr(collect, "parse_hotlist", lambda md: _hot_rows(2))
    monkeypatch.setattr(collect, "STATE_FILE", str(tmp_path / "state.json"))
    _login_state(tmp_path)
    monkeypatch.setattr(collect, "PROVIDERS", {"local": lambda kw, n: []})
    with pytest.raises(RuntimeError, match="未抓到视频"):
        collect.run_round("local", rounds=1, top_n=10, mode="real")
    # 不应写出空 CSV
    assert not list((tmp_path / "collect").glob("videos_*.csv"))