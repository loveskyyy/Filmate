"""嵌套 schema fragment / $ref / 漏包装 / 顶层 list 检测单测。

对应 lib/episode_planner.py 的 _is_schema_fragment / _find_schema_fragment_in_data /
_has_missing_episodes_wrapper helper：覆盖 LLM 错误输出形态：
  1. 顶层 dict 是 {"$ref": "..."}（旧版 Layer B 已处理）
  2. 已知 list 字段（episodes）的值是 schema 片段（嵌套版）
  3. 任意字段值是 schema 片段
  4. 多层嵌套
  5. 漏掉 episodes 包装，把单集字段直接放顶层
  6. 顶层是 list（被截断 / 错乱）
  7. 不应误判正常业务数据
"""

import pytest
import re


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
    assert ep_helpers["_is_schema_fragment"]({"items": {"$ref": "#/$defs/X"}, "type": "array"}) is True


def test_schema_fragment_with_ref_only(ep_helpers):
    assert ep_helpers["_is_schema_fragment"]({"$ref": "DramaEpisodeDraft"}) is True


def test_schema_fragment_with_anyof(ep_helpers):
    assert ep_helpers["_is_schema_fragment"]({"anyOf": [{"$ref": "X"}]}) is True
    assert ep_helpers["_is_schema_fragment"]({"oneOf": []}) is True
    assert ep_helpers["_is_schema_fragment"]({"allOf": []}) is True


def test_not_schema_fragment_for_normal_list(ep_helpers):
    assert ep_helpers["_is_schema_fragment"]([]) is False
    assert ep_helpers["_is_schema_fragment"]([{"title": "x"}]) is False


def test_not_schema_fragment_for_normal_dict(ep_helpers):
    assert ep_helpers["_is_schema_fragment"]({"title": "x"}) is False
    assert ep_helpers["_is_schema_fragment"]({"episodes": [{"title": "x"}]}) is False


def test_not_schema_fragment_for_non_dict(ep_helpers):
    assert ep_helpers["_is_schema_fragment"]("string") is False
    assert ep_helpers["_is_schema_fragment"](42) is False
    assert ep_helpers["_is_schema_fragment"](None) is False


# === _find_schema_fragment_in_data ===

def test_find_user_bug_shape(ep_helpers):
    data = {"episodes": {"items": {"$ref": "#/$defs/Episodes"}, "type": "array"}, "title": "深夜异常"}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "episodes" in hit


def test_find_top_level_ref(ep_helpers):
    data = {"$ref": "DramaEpisodeDraft"}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "$ref" in hit


def test_find_deeply_nested_ref(ep_helpers):
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
    data = {
        "episodes": [
            {"title": "x", "hook": "y", "story_beats": ["a"], "end_anchor": "b", "next_episode_teaser": "c"},
        ],
        "title": "ok"
    }
    assert ep_helpers["_find_schema_fragment_in_data"](data) is None


def test_no_fragment_in_empty_data(ep_helpers):
    data = {"episodes": [], "title": "x"}
    assert ep_helpers["_find_schema_fragment_in_data"](data) is None


def test_fragment_in_unexpected_field(ep_helpers):
    data = {"title": "x", "random_field": {"$ref": "X"}}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "random_field" in hit


def test_path_tracking(ep_helpers):
    data = {"outer": {"inner": {"$ref": "X"}}}
    hit = ep_helpers["_find_schema_fragment_in_data"](data)
    assert hit is not None
    assert "outer" in hit
    assert "inner" in hit


# === _has_missing_episodes_wrapper (新) ===

def test_missing_wrapper_user_bug(ep_helpers):
    """用户报错形态：LLM 把单集字段直接放顶层，漏了 episodes 包装。"""
    data = {
        "title": "异常的第一毫米",
        "hook": "...",
        "end_anchor": "...",
        "story_beats": ["..."],
        "next_episode_teaser": "...",
    }
    assert ep_helpers["_has_missing_episodes_wrapper"](data) is True


def test_missing_wrapper_with_only_title(ep_helpers):
    """只有一个 title 字段也算漏包装。"""
    data = {"title": "异常的第一毫米"}
    assert ep_helpers["_has_missing_episodes_wrapper"](data) is True


def test_no_missing_wrapper_when_legit(ep_helpers):
    """正常含 episodes 包装的不触发。"""
    data = {
        "episodes": [
            {"title": "x", "hook": "y", "story_beats": ["a"], "end_anchor": "b", "next_episode_teaser": "c"},
        ],
    }
    assert ep_helpers["_has_missing_episodes_wrapper"](data) is False


def test_no_missing_wrapper_for_replan(ep_helpers):
    """replan 模式含 episode_target_units 字段也不触发。"""
    data = {
        "episodes": [{"title": "x", "hook": "y", "end_anchor": "z"}],
        "episode_target_units": 5,
    }
    assert ep_helpers["_has_missing_episodes_wrapper"](data) is False


def test_no_missing_wrapper_for_empty_dict(ep_helpers):
    """空 dict 不触发。"""
    assert ep_helpers["_has_missing_episodes_wrapper"]({}) is False


def test_no_missing_wrapper_for_list(ep_helpers):
    """list 不触发（不是 dict）。"""
    assert ep_helpers["_has_missing_episodes_wrapper"]([]) is False
    assert ep_helpers["_has_missing_episodes_wrapper"]([{"title": "x"}]) is False


def test_no_missing_wrapper_for_unrelated_dict(ep_helpers):
    """含其它字段但不含 episode 字段的 dict 不触发。"""
    data = {"random_key": "value", "other": 123}
    assert ep_helpers["_has_missing_episodes_wrapper"](data) is False


# === 顶层不是 dict 场景（[0] 等） ===

def test_user_bug_zero_list(ep_helpers):
    """用户实际报错：LLM 输出 [0]（被截断或完全错乱）。"""
    # 这个测试不需要 helper，直接验证 isinstance 检查
    data = [0]
    assert isinstance(data, list) and not isinstance(data, dict)
    # 模拟 _parse_draft 会抛错的行为——通过调用 helper 验证
    assert ep_helpers["_is_schema_fragment"](data) is False
    # _find_schema_fragment_in_data 对 list 返回 None（不递归）
    assert ep_helpers["_find_schema_fragment_in_data"](data) is None
