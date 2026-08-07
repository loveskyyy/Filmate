"""_try_recover_dict 单测：覆盖常见污染场景与正常输入。"""

import pytest

from lib.script_generator import _try_recover_dict


def test_recovers_dict_from_clean_json():
    """纯 JSON 对象直接返回。"""
    text = '{"title": "t", "video_units": []}'
    assert _try_recover_dict(text) == {"title": "t", "video_units": []}


def test_recovers_dict_from_think_plus_json():
    """<think> 块 + 后续 JSON 对象：先剥 think 再找 object 即可命中。"""
    text = '<think>[3, 4, 3, 5] = 15s</think>\n```json\n{"title": "t"}\n```'
    result = _try_recover_dict(text)
    assert result == {"title": "t"}


def test_returns_none_when_only_list():
    """响应里只有 list（用户报错场景），没有 object 时返回 None。"""
    text = "[3, 4, 3, 5]"
    assert _try_recover_dict(text) is None


def test_recovers_dict_when_list_precedes_object():
    """响应前段是 list 片段、后段是真正的 object（provider 抽取 bug）。"""
    text = 'Preamble: [3, 4, 3, 5] as sample.\nReal: {"title": "t", "video_units": []}'
    result = _try_recover_dict(text)
    assert result == {"title": "t", "video_units": []}


def test_handles_nested_braces_in_string():
    """字符串里含 {curly} 不能误判为 JSON 嵌套。"""
    text = '{"title": "x", "video_units": [{"shots": [{"text": "a {curly} b"}]}]}'
    result = _try_recover_dict(text)
    assert result["title"] == "x"
    assert result["video_units"][0]["shots"][0]["text"] == "a {curly} b"


def test_returns_none_for_empty_string():
    assert _try_recover_dict("") is None
    assert _try_recover_dict("   ") is None


def test_returns_none_for_non_string():
    assert _try_recover_dict(None) is None
    assert _try_recover_dict(123) is None


def test_does_not_match_unrelated_dict_without_known_keys():
    """含 {} 但无已知剧本字段的字典不应当作 valid script。"""
    text = '{"random_key": "value", "another": [1, 2, 3]}'
    assert _try_recover_dict(text) is None
