"""面向字符串的文本预处理工具。"""

from __future__ import annotations

import re

# 开栏：``` 后可跟空白、可选的语言标注 json（大小写不敏感）、可选空白与换行。
# 兼容 ```json / ```JSON / ``` json / ```  JSON 等带空格变体。
_OPENING_FENCE = re.compile(r"^```[ \t]*(?:json)?[ \t]*\n?", re.IGNORECASE)
# 闭栏：结尾的 ``` 及其前导换行。
_CLOSING_FENCE = re.compile(r"\n?```$")


def strip_json_code_fences(text: str) -> str:
    """剥离 LLM 输出最外层的 markdown 代码栅栏，返回可交给 json.loads 的纯文本。

    两端去空白后：剥离开头的 ``` 栅栏（可带空白与可选的 json 语言标注，大小写不敏感，
    兼容 ```JSON / ```Json / ``` json / ```  JSON 等变体），再剥离结尾的 ``` 闭栏；最后去空白返回。
    无栅栏的裸 JSON 仅做两端 strip。
    """
    text = text.strip()
    text = _OPENING_FENCE.sub("", text)
    text = _CLOSING_FENCE.sub("", text)
    return text.strip()

# 防御 LLM 思考块污染：MiniMax-M3 等带 CoT 的模型即使在 strict json_schema 通道下，
# 响应里仍会塞入 <think>...</think> 块。供应商解析器可能从思考块里抠出字面数组
# （如 `[3, 4, 3, 5]`）当成响应主体，导致 Pydantic 校验时报"Input should be an object,
# input_value=[3, 4, 3, 5], input_type=list"。剥离思考块让真正的 JSON 代码块成为响应中
# 唯一结构化输出。注意只在解析前做剥离，原始 LLM 响应不丢（仍写在 arcreel.log 供排查）。
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_blocks(text: str) -> str:
    """剥离 LLM 输出中的 <think>...</think> 思考块，返回剩余文本。

    无思考块时原样返回（除两端 strip）。不影响 markdown 栅栏、JSON 内容或其它文本。
    多次出现也全部剥离；嵌套 <think> 块按非贪婪匹配最外层。
    """
    if not isinstance(text, str):
        return text
    return _THINK_BLOCK_RE.sub("", text).strip()
