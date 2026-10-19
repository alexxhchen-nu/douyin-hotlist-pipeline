from pathlib import Path
from unittest import mock

import pytest

import hotlist


SAMPLE = '''
# 抖音热榜

- ![](https://lf-douyin-pc-web.douyinstatic.com/obj/douyin-pc-web/ies/douyin_web//icons/hot/up.svg)


[**置顶条目不属于榜单**](https://www.douyin.com/hot/9999999/xxx)

- ![](https://lf-douyin-pc-web.douyinstatic.com/obj/douyin-pc-web/ies/douyin_web//icons/hot/hot_top1.svg)


[**中国队列第一**](https://www.douyin.com/hot/2700001/xxx)


11160.2K热度

- ![](https://lf-douyin-pc-web.douyinstatic.com/obj/douyin-pc-web/ies/douyin_web//icons/hot/hot_top2.svg)


[**南北吃蟹大不同**](https://www.douyin.com/hot/2700002/xxx)


11103.3K热度

- 3


[**嫁金钗晋江式演技模仿**](https://www.douyin.com/hot/2700003/xxx)


11100.9K热度

抖音热榜规则说明
'''


def test_parse_skips_pinned_item():
    rows = hotlist.parse_hotlist(SAMPLE)
    assert len(rows) == 3
    assert rows[0]["title"] == "中国队列第一"
    assert rows[0]["rank"] == 1
    assert rows[0]["hot_value_k"] == "11160.2"
    assert all("置顶" not in r["title"] for r in rows)


def test_parse_ranks_are_continuous():
    rows = hotlist.parse_hotlist(SAMPLE)
    ranks = [r["rank"] for r in rows]
    assert ranks == [1, 2, 3]


def test_parse_heat_value_pairs_correctly():
    rows = hotlist.parse_hotlist(SAMPLE)
    assert rows[1]["hot_value_k"] == "11103.3"
    assert rows[2]["hot_value_k"] == "11100.9"


def test_parse_empty_raises_no_crash():
    assert hotlist.parse_hotlist("no hot list here") == []


def test_fetch_requires_cookie():
    with mock.patch.object(hotlist, "DOUYIN_HOT_COOKIE", ""):
        with pytest.raises(RuntimeError, match="DOUYIN_HOT_COOKIE"):
            hotlist.fetch_hot_markdown()


def test_write_csv_roundtrip(tmp_path):
    rows = [
        {"rank": 1, "title": "A", "hot_url": "u1", "hot_id": "1", "hot_value_k": "1.0", "fetched_at": "t"},
        {"rank": 2, "title": "B", "hot_url": "u2", "hot_id": "2", "hot_value_k": "2.0", "fetched_at": "t"},
    ]
    out = hotlist.write_csv(rows, Path(tmp_path) / "hot.csv")
    text = out.read_text(encoding="utf-8-sig")
    assert "rank,title" in text
    assert "A" in text and "B" in text