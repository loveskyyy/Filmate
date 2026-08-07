"""嵌套 schema fragment / $ref 检测单测。

对应 lib/episode_planner.py 的 _is_schema_fragment 和 _find_schema_fragment_in_data
helper：覆盖 LLM 错误地把 JSON Schema 片段当成业务数据输出的常见 bug，包括：
  1. 顶层 dict 是 {"$ref": "..."}（旧版 Layer B 已处理）
  2. 已知 list 字段（episodes）的值是 schema 片段（嵌套版，本次新增覆盖）
  3. 任意字段值是 schema 片段
  4. 多层嵌套
  5. 不应误判正常业务数据
"""

import pytest

# 由于 lib.episode_planner 在 import 时会触发循环导入（lib.text_backends.gemini ↔
# lib.custom_provider.endpoints），测试在容器里只能通过 exec 提取 helper 源码再执行。
# 这种方式与生产 import 一致，不影响功能验证。
import re
import sys
import types


@pytest.fixture(scope="module")
def ep_helpers():
    src = open("/app/lib/episode_planner.py", encoding="utf-8").read()
    m_start = re.search(r"^# 已知.列表型.剧本字段", src, re.M)
    m_end = re.search(r"^class EpisodePlanner", src, re.M)
    if not m_start or not m_end:
        pytest.skip("episode_planner.py 结构不符合预期，helper 提取失败")
    helper_src = src[m_start.start():m_end.start()].rstrip() + "\n"
    ns = {}
    exec(helper_src, ns)
    return ns


# === _is_schema_fragment ===

def test_schema_fragment_with_items_and_type(ep_helpers):
    """{"items": {...}, "type": "array"} 是 schema 片段（最常见 bug 形态）。"""
    assert ep_helpers["_is_schema_fragment"]({"items": {"$ref": "#/$defs/X"}, "type": "array"}) is True


def test_schema_fragment_with_ref_only(ep_helpers):
    """{"$ref": "..."} 单字段也是 schema 片段。"""
    assert ep_helpers["_is_schema_fragment"]({"$ref": "DramaEpisodeDraft"}) is True


def test_schema_fragment_with_anyof(ep_helpers):
    """anyOf / oneOf / allOf 是 schema 关键字。"""
    assert ep_helpers["_is_schema_fragment"]({"anyOf": [{"$ref": "X"}]}) is True
    assert ep_helpers["_is_schema_fragment"]({"oneOf": []}) is True
    assert ep_helpers["_is_schema_fragment"]({"allOf": []}) is True


def test_not_schema_fragment_for_normal_list(ep_helpers):
    """list 值不是 schema 片段（_is_schema_fragment 只对 dict 判定）。"""
    assert ep_helpers["_is_schema_fragment"]([]) is False
    assert ep_helpers["_is_schema_fragment"]([{"title": "x"}]) is False


def test_not_schema_fragment_for_normal_dict(ep_helpers):
    """业务数据 dict 不应被误判。"""
    assert ep_helpers["_is_schema_fragment"]({"title": "x"}) is False
    assert ep_helpers["_is_schema_fragment"]({"episodes": [{"title": "x"}]}) is False
    assert ep_helpers["_is_schema_fragment"]({"title": "x", "hook": "y", "story_beats": ["a"]}) is False


def test_not_schema_fragment_for_non_dict(ep_helpers):
    """非 dict 永远不是 schema 片段。"""
    assert ep_helpers["_is_schema_fragment"]("string") is False
    assert ep_helpers["_is_schema_fragment"](42) is False
    assert ep_helpers["_is_schema_fragment"](None) is False


# === _find_schema_fragment_in_data ===

def test_find_user_bug_shape(ep_helpers):
    """用户实际报错形态：episodes 字段值是 items+type 片段。"""
    data = {"episodes": {"items": {"$ref": "#/$defs/Episodes"}, "type": "array"}, "title": "深夜异常"}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "episodes" in hit
    assert "$ref" in hit or "items" in hit


def test_find_top_level_ref(ep_helpers):
    """顶层 $ref 也应被定位（虽然旧 Layer B 已拦截，这里确认新 helper 也能识别）。"""
    data = {"$ref": "DramaEpisodeDraft"}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "$ref" in hit


def test_find_deeply_nested_ref(ep_helpers):
    """多层嵌套也必须定位（递归到 dict 子节点）。"""
    data = {
        "episodes": {
            "items": {
                "properties": {
                    "title": {"type": "string"}
                }
            }
        }
    }
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None


def test_no_fragment_in_legit_data(ep_helpers):
    """正常业务数据不触发。"""
    data = {
        "episodes": [
            {"title": "x", "hook": "y", "story_beats": ["a"], "end_anchor": "b", "next_episode_teaser": "c"},
            {"title": "x2", "hook": "y2", "story_beats": ["a2"], "end_anchor": "b2", "next_episode_teaser": "c2"},
        ],
        "title": "ok"
    }
    assert ep_helpers["_find_schema_fragment_in_data"](data) is None


def test_no_fragment_in_empty_data(ep_helpers):
    """空 episodes 数组不触发。"""
    data = {"episodes": [], "title": "x"}
    assert ep_helpers["_find_schema_fragment_in_data"](data) is None


def test_fragment_in_unexpected_field(ep_helpers):
    """schema 片段出现在非已知字段时也应拦截（防御 instructor bug 把 schema 注入到任何字段）。"""
    data = {"title": "x", "random_field": {"$ref": "X"}}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "random_field" in hit


def test_path_tracking(ep_helpers):
    """返回的 path 应能定位到具体嵌套层级。"""
    data = {"outer": {"inner": {"$ref": "X"}}}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "outer" in hit
    assert "inner" in hit
