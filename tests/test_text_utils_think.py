"""strip_think_blocks 单测：覆盖有/无 think 块、多块、嵌套、纯文本、None 等输入。"""

import pytest

from lib.text_utils import strip_think_blocks


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 1. 无 think 块
        ('{"a": 1}', '{"a": 1}'),
        ('plain text', 'plain text'),
        # 2. 单个 think 块
        ('<think>reasoning</think> {"a": 1}', '{"a": 1}'),
        # 3. 多个 think 块
        ('<think>a</think> text <think>b</think> more', 'text  more'),
        # 4. think 块在中间
        ('prefix<think>reasoning</think> suffix', 'prefix suffix'),
        # 5. think 块内含特殊字符（含数组、JSON-like）
        ('<think>[3, 4, 3, 5] = 15s</think> {"a": 1}', '{"a": 1}'),
        # 6. think 块跨多行
        ('<think>\nmulti\nline\nthinking\n</think>\n{"a": 1}', '{"a": 1}'),
        # 7. None / 非字符串
        (None, None),
        (123, 123),
    ],
)
def test_strip_think_blocks(raw, expected):
    """剥离 <think>...</think> 块，其它内容原样保留。"""
    assert strip_think_blocks(raw) == expected


def test_strip_think_blocks_preserves_markdown_fences():
    """think 块剥离后，markdown 栅栏应保留给后续 strip_json_code_fences 处理。"""
    text = '<think>thinking</think>\n```json\n{"a": 1}\n```'
    out = strip_think_blocks(text)
    assert "```json" in out
    assert "<think>" not in out


def test_strip_think_blocks_strip_in_parse_response():
    """回归测试：think 块 + json 代码块组合可被 _parse_response 正确解析。"""
    from lib.text_utils import strip_json_code_fences, strip_think_blocks

    text = '<think>[3, 4, 3, 5] = 15s</think>\n```json\n{"a": 1}\n```'
    # 必须先剥 think，再剥 markdown
    cleaned = strip_json_code_fences(strip_think_blocks(text))
    import json
    assert json.loads(cleaned) == {"a": 1}
