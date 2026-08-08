"""Instructor 降级支持 — 为不支持原生结构化输出的模型提供 prompt 注入 + 解析 + 重试。"""

from __future__ import annotations

import json
import logging
from typing import get_args, get_origin

import instructor
from instructor import Mode
from instructor.core import IncompleteOutputException
from pydantic import BaseModel, ValidationError

from lib.text_backends.base import TextGenerationResult, TextOutputTruncatedError, TokenParam, check_truncation
from lib.text_utils import strip_json_code_fences, strip_think_blocks

logger = logging.getLogger(__name__)


def _output_tokens_from_incomplete(exc: IncompleteOutputException) -> int | None:
    """尽力从截断异常携带的部分响应里取 output_tokens，取不到则 None（不阻断异常转换）。"""
    usage = getattr(getattr(exc, "last_completion", None), "usage", None)
    return getattr(usage, "completion_tokens", None) if usage else None


def generate_structured_via_instructor(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
    max_tokens: int | None = None,
    token_param: TokenParam = "max_tokens",
    provider: str = "",
) -> tuple[str, int | None, int | None]:
    """通过 Instructor 生成结构化输出（同步版，供 Ark 等同步 SDK 使用）。

    token_param 决定 max_tokens 值在导线上的参数名，由调用方按端点选择。
    返回 (json_text, input_tokens, output_tokens)。Instructor 的
    ``IncompleteOutputException``（输出被 max_tokens 截断）归一为 :class:`TextOutputTruncatedError`，
    与原生结构化通道的截断行为同口径（见 docs/adr/0044）。
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() 返回 None — client 类型 {type(client).__name__} 不受支持，"
            "请传入 openai.OpenAI 或 openai.AsyncOpenAI 实例"
        )
    extra: dict = {token_param: max_tokens} if max_tokens is not None else {}
    try:
        result, completion = patched.chat.completions.create_with_completion(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_model=response_model,
            max_retries=max_retries,
            **extra,
        )
    except IncompleteOutputException as exc:
        raise TextOutputTruncatedError(
            provider=provider, model=model, output_tokens=_output_tokens_from_incomplete(exc)
        ) from exc
    json_text = result.model_dump_json()

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


async def generate_structured_via_instructor_async(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
    max_tokens: int | None = None,
    token_param: TokenParam = "max_tokens",
    provider: str = "",
) -> tuple[str, int | None, int | None]:
    """通过 Instructor 生成结构化输出（异步版，供 OpenAI AsyncOpenAI 使用）。

    token_param 决定 max_tokens 值在导线上的参数名，由调用方按端点选择。
    返回 (json_text, input_tokens, output_tokens)。Instructor 的
    ``IncompleteOutputException``（输出被 max_tokens 截断）归一为 :class:`TextOutputTruncatedError`，
    与原生结构化通道的截断行为同口径（见 docs/adr/0044）。
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() 返回 None — client 类型 {type(client).__name__} 不受支持，"
            "请传入 openai.OpenAI 或 openai.AsyncOpenAI 实例"
        )
    extra: dict = {token_param: max_tokens} if max_tokens is not None else {}
    try:
        result, completion = await patched.chat.completions.create_with_completion(  # type: ignore[misc]
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_model=response_model,
            max_retries=max_retries,
            **extra,
        )
    except IncompleteOutputException as exc:
        raise TextOutputTruncatedError(
            provider=provider, model=model, output_tokens=_output_tokens_from_incomplete(exc)
        ) from exc
    json_text = result.model_dump_json()

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


def inject_json_instruction(messages: list[dict]) -> list[dict]:
    """向 messages 注入 JSON 格式指令，确保 json_object 模式可用。

    OpenAI API 要求 prompt 中包含 "JSON" 关键字才能启用 json_object 模式。
    若 messages 中已包含 "JSON"，则原样返回副本。
    """
    fb_messages = list(messages)
    if any("JSON" in (m.get("content") or "") for m in fb_messages):
        return fb_messages
    sys_idx = next((i for i, m in enumerate(fb_messages) if m.get("role") == "system"), None)
    if sys_idx is not None:
        orig = fb_messages[sys_idx]
        fb_messages[sys_idx] = {**orig, "content": (orig.get("content") or "") + "\nRespond in JSON format."}
    else:
        fb_messages.insert(0, {"role": "system", "content": "Respond in JSON format."})
    return fb_messages


def instructor_fallback_sync(
    client,
    model: str,
    messages: list[dict],
    response_schema: dict | type[BaseModel] | None,
    provider: str,
    max_tokens: int | None = None,
    token_param: TokenParam = "max_tokens",
):
    """同步 Instructor 降级路径。

    - response_schema 为 Pydantic 类 → instructor create_with_completion
    - response_schema 为 dict → inject JSON instruction + json_object 模式

    供 Ark 等同步 SDK 后端使用（调用方用 asyncio.to_thread 包装）。
    不做重试，瞬态错误由调用方的重试循环统一处理。
    """
    if isinstance(response_schema, type):
        json_text, input_tokens, output_tokens = generate_structured_via_instructor(
            client=client,
            model=model,
            messages=messages,
            response_model=response_schema,
            max_tokens=max_tokens,
            token_param=token_param,
            provider=provider,
        )
        return TextGenerationResult(
            text=json_text,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    logger.info("response_schema 为 dict，无法使用 Instructor，回退到 json_object 模式")
    fb_messages = inject_json_instruction(messages)
    create_kwargs: dict = {
        "model": model,
        "messages": fb_messages,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        create_kwargs[token_param] = max_tokens
    response = client.chat.completions.create(**create_kwargs)
    usage = getattr(response, "usage", None)
    choice = response.choices[0]
    text = choice.message.content or ""
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None
    # dict schema 仍是结构化输出诉求（response_schema 非空，只是无 Pydantic 模型可走原生
    # Instructor 通道），截断同样升级为硬错误。
    check_truncation(
        getattr(choice, "finish_reason", None),
        provider=provider,
        model=model,
        output_tokens=output_tokens,
        structured=True,
    )
    return TextGenerationResult(
        text=text.strip() if isinstance(text, str) else str(text),
        provider=provider,
        model=model,
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=output_tokens,
    )


async def instructor_fallback_async(
    client,
    model: str,
    messages: list[dict],
    response_schema: dict | type[BaseModel] | None,
    provider: str,
    max_tokens: int | None = None,
    token_param: TokenParam = "max_tokens",
):
    """异步 Instructor 降级路径。

    - response_schema 为 Pydantic 类 → instructor create_with_completion (async)
    - response_schema 为 dict → inject JSON instruction + json_object 模式 (async)

    供 OpenAI 等原生异步 SDK 后端使用。
    不做重试，瞬态错误由调用方的重试循环统一处理。

    Layer B 路径：优先用 ``generate_structured_with_layer_b_async`` —— 针对
    minimaxi 这类不强 schema 的 provider 提供 4 类错误的诊断反馈：
    (1) 顶层类型错（list 当 object）、(2) 顶层 schema 片段（$ref / type）、
    (3) 嵌套 $ref / schema 片段、(4) 缺顶层包装（嵌套模型字段平铺到顶层）。
    失败兜底走原生 instructor 重试。
    """
    from lib.text_backends.base import TextGenerationResult

    if isinstance(response_schema, type):
        # 优先 Layer B 路径，给 LLM 具体反馈而不是 instructor 的通用 pydantic 报错
        try:
            json_text, input_tokens, output_tokens = await generate_structured_with_layer_b_async(
                client=client,
                model=model,
                messages=messages,
                response_model=response_schema,
                max_tokens=max_tokens,
                token_param=token_param,
                provider=provider,
            )
            return TextGenerationResult(
                text=json_text,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except ValueError as exc:
            # Layer B 重试用完（最常见：JSON parse 持续失败 / 4 类错误 LLM 都救不回）
            # 兜底回原生 instructor 重试一遍——它会用 Pydantic 错误消息再试，
            # 有时换个角度能救。
            logger.warning(
                "Layer B 重试耗尽（%s），回退到原生 instructor 路径", exc,
            )
            json_text, input_tokens, output_tokens = await generate_structured_via_instructor_async(
                client=client,
                model=model,
                messages=messages,
                response_model=response_schema,
                max_tokens=max_tokens,
                token_param=token_param,
                provider=provider,
            )
            return TextGenerationResult(
                text=json_text,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

    logger.info("response_schema 为 dict，无法使用 Instructor，回退到 json_object 模式")
    fb_messages = inject_json_instruction(messages)
    create_kwargs: dict = {
        "model": model,
        "messages": fb_messages,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        create_kwargs[token_param] = max_tokens
    response = await client.chat.completions.create(**create_kwargs)
    usage = getattr(response, "usage", None)
    choice = response.choices[0]
    text = choice.message.content or ""
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None
    # dict schema 仍是结构化输出诉求（response_schema 非空，只是无 Pydantic 模型可走原生
    # Instructor 通道），截断同样升级为硬错误。
    check_truncation(
        getattr(choice, "finish_reason", None),
        provider=provider,
        model=model,
        output_tokens=output_tokens,
        structured=True,
    )
    return TextGenerationResult(
        text=text.strip() if isinstance(text, str) else str(text),
        provider=provider,
        model=model,
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=output_tokens,
    )


# =====================================================================
# Layer B: 自定义结构化输出重试（针对 minimaxi 这类不强 schema 的 provider）
# =====================================================================
#
# 背景：minimaxi 的 response_format=json_schema 不强制约束，LLM 经常会返回
# "近 schema 但结构错"的输出，instructor 的通用 Pydantic retry 只能反复说
# "Input should be an object" 之类的话，LLM 听不懂。Layer B 在 LLM 重试时
# 注入具体诊断 + 示例，让 LLM 知道该怎么修。
#
# 拦截的 4 类错误（按顺序）：
#   1. 顶层类型错：LLM 返回 list / 字符串 / 数字，但 Pydantic model 要求 object
#   2. 顶层 schema 片段：dict 含 `type` 或 `$ref`，是 schema 定义本身不是数据
#   3. 嵌套 schema 片段：树中某字段值是 schema 片段（典型：items / properties 含 $ref）
#   4. 缺顶层包装：嵌套模型的字段被平铺到顶层（如 DramaPlanDraft 期望
#      `{"episodes": [...]}`，LLM 返回 `{"title": ..., "hook": ..., ...}`）


# JSON Schema 标准 type 名称
_JSON_SCHEMA_TYPE_NAMES: frozenset[str] = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)

# 单纯 schema 才会出现的关键字（real data 不会带这些 key）
_SCHEMA_FRAGMENT_KEYS: frozenset[str] = frozenset(
    {
        "type", "$ref", "items", "properties", "additionalProperties",
        "anyOf", "oneOf", "allOf", "$defs", "definitions",
        "required", "enum", "format", "pattern",
        "minLength", "maxLength", "minimum", "maximum",
        "minItems", "maxItems", "uniqueItems",
        "minProperties", "maxProperties",
    }
)


def _is_top_level_schema_fragment(value) -> bool:
    """判断 value 是不是 JSON Schema 片段（而不是真实数据）。

    判定规则（命中任一即返回 True）：
    - 含 ``$ref`` 字符串键
    - ``type`` 值在 JSON Schema 标准类型集合里 *且* 至少有一个 schema 关键字
      （items / properties / $ref / anyOf / oneOf / allOf）一起出现

    设计要点：``type`` 单独出现可能也是合法业务字段，所以必须和 schema 关键字
    共现才算。``$ref`` 单独出现就是 schema 引用。
    """
    if not isinstance(value, dict):
        return False
    if "$ref" in value and isinstance(value["$ref"], str):
        return True
    type_val = value.get("type")
    if isinstance(type_val, str) and type_val in _JSON_SCHEMA_TYPE_NAMES:
        if any(k in value for k in _SCHEMA_FRAGMENT_KEYS - {"type"}):
            return True
    return False


def _find_schema_fragment_in_data(data, path: str = "") -> list[str]:
    """递归找 data 中所有 schema 片段的位置（用 path 标记，如 "video_units" 或 "items[2]"）。

    用于诊断反馈，让 LLM 知道具体哪个字段还残留 schema。
    """
    fragments: list[str] = []
    if isinstance(data, dict):
        if _is_top_level_schema_fragment(data):
            fragments.append(path or "<root>")
            return fragments  # 命中即返回，不再下钻
        for k, v in data.items():
            sub = f"{path}.{k}" if path else k
            fragments.extend(_find_schema_fragment_in_data(v, sub))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            fragments.extend(_find_schema_fragment_in_data(item, f"{path}[{i}]"))
    return fragments


def _extract_pydantic_models_from_annotation(annotation) -> list:
    """递归从 list[Model] / Optional[list[Model]] / Union[...] 里抽出所有 BaseModel 子类。

    用于 ``_has_missing_wrapper``：要把嵌套类型深度展开，找到真正可能对应的
    Pydantic 模型。
    """
    result: list = []
    origin = get_origin(annotation)
    if origin is list:
        for arg in get_args(annotation):
            result.extend(_extract_pydantic_models_from_annotation(arg))
    elif origin is not None:  # Union / Optional
        for arg in get_args(annotation):
            if arg is not type(None):
                result.extend(_extract_pydantic_models_from_annotation(arg))
    else:
        result.append(annotation)
    return result


def _has_missing_wrapper(data, model: type[BaseModel]) -> bool:
    """检查 data 是否是嵌套模型字段平铺到顶层（缺少 wrapper）。

    真实案例：DramaPlanDraft 顶层是 ``episodes: list[DramaEpisodeDraft]``，
    LLM 直接返回 ``{title, hook, end_anchor, story_beats}``（DramaEpisodeDraft
    字段），缺了 ``episodes`` 包装。

    判定：
    1. data 不是顶层 wrapper（顶层 keys 与 model.model_fields 无交集）
    2. data 的 keys 完整等于 model 某个字段的 Pydantic 子模型的 fields

    第二个条件用 ``set equality`` 而非 subset，避免 "恰好包含嵌套 fields + 误打 wrapper"
    的模糊情况。子模型通过 ``_extract_pydantic_models_from_annotation`` 递归展开，
    支持 ``list[Model]``、``Optional[list[Model]]``、``Union[Model, None]`` 等。
    """
    if not isinstance(data, dict) or not hasattr(model, "model_fields"):
        return False
    model_fields = set(model.model_fields.keys())
    data_keys = set(data.keys())
    # 顶层 keys 与 model 任何字段名重合 → 不是平铺
    if data_keys & model_fields:
        return False
    # 遍历 model 的每个字段，递归抽出所有嵌套 Pydantic 子模型，看有没有
    # 子模型的 fields 与 data_keys 完全相等
    for field_info in model.model_fields.values():
        inner_models = _extract_pydantic_models_from_annotation(field_info.annotation)
        for inner in inner_models:
            if hasattr(inner, "model_fields"):
                inner_fields = set(inner.model_fields.keys())
                if data_keys == inner_fields:
                    return True
    return False


async def generate_structured_with_layer_b_async(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    max_retries: int = 2,
    max_tokens: int | None = None,
    token_param: TokenParam = "max_tokens",
    provider: str = "",
) -> tuple[str, int | None, int | None]:
    """Layer B 异步版：自定义重试 + 诊断反馈。

    与 ``generate_structured_via_instructor_async`` 区别：
    - 不走 instructor 的 ``MD_JSON`` 模式包装（那样只会反复说 "Input should
      be an object"，LLM 听不懂）
    - 直接调 ``client.chat.completions.create`` + ``response_format=json_object``
    - 每次返回后做 4 类 Layer B 检测 + Pydantic 校验；任一失败就把具体诊断
      作为 user message 追加到 messages，让 LLM 下一轮自我修正
    - 重试用尽抛 ``ValueError``（兜底逻辑在 :func:`instructor_fallback_async`
      里，会回退到原生 instructor 路径再试一次）
    """
    feedback: str | None = None
    last_data = None  # debug
    for attempt in range(1, max_retries + 2):  # max_retries+1 次尝试
        # 拼装当前 messages：只在非首轮追加反馈
        current_messages = messages
        if feedback is not None:
            current_messages = list(messages) + [
                {"role": "user", "content": (
                    f"你上一次的输出不符合 schema：\n\n{feedback}\n\n"
                    f"请重新输出完整、合法的 JSON object（顶层必须是 object，不能是 list / 字符串 / 数字）。"
                )}
            ]
        # 调 LLM（不抛异常给外层：网络/API 错误由调用方重试处理）
        response = await client.chat.completions.create(
            model=model,
            messages=current_messages,  # type: ignore[arg-type]
            response_format={"type": "json_object"},
            **({token_param: max_tokens} if max_tokens is not None else {}),
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        output_tokens = response.usage.completion_tokens if response.usage else None
        # 截断 = 硬错误（与原生通道同口径）
        check_truncation(
            getattr(choice, "finish_reason", None),
            provider=provider,
            model=model,
            output_tokens=output_tokens,
            structured=True,
        )
        # 清 think block /  markdown fence（与原生 _parse_response 口径一致）
        cleaned = strip_json_code_fences(strip_think_blocks(text))
        # 解析 JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            feedback = f"输出不是有效 JSON：{exc.msg}（位置 {exc.pos}）。请只输出合法 JSON object，不要夹带解释或 markdown。"
            continue
        last_data = data
        # ===== Layer B 检测 #1：顶层类型错 =====
        if not isinstance(data, dict):
            preview = repr(data)[:100]
            feedback = (
                f"输出类型不对：收到了 {type(data).__name__}（如 {preview}），"
                f"但 schema 要求一个 JSON object（dict）。请把数据包装成 object："
                f"顶层是 ``{{...}}``，包含 schema 要求的字段。"
            )
            continue
        # ===== Layer B 检测 #2：顶层 schema 片段 =====
        if _is_top_level_schema_fragment(data):
            feedback = (
                "你输出的顶层看起来是 JSON Schema 定义（含 ``type`` / ``$ref`` 等 schema 关键字），"
                "不是实际数据。请输出符合 schema 的实际数据值，"
                "示例：``{{\"title\": \"剧名\", \"video_units\": [{{\"unit_id\": \"E1U1\", ...}}]}}``。"
            )
            continue
        # ===== Layer B 检测 #3：嵌套 schema 片段 =====
        nested = _find_schema_fragment_in_data(data)
        if nested:
            shown = "\n".join(f"  - {p}" for p in nested[:3])
            feedback = (
                "你的输出在以下字段还残留 JSON Schema 片段（含 ``$ref`` / ``type`` / ``items`` 等 schema 关键字）：\n"
                f"{shown}\n"
                "请把对应字段替换为符合 schema 的实际数据值，不要再输出 schema 本身。"
            )
            continue
        # ===== Layer B 检测 #4：缺顶层包装 =====
        if _has_missing_wrapper(data, response_model):
            expected_top = list(response_model.model_fields.keys())
            feedback = (
                f"你输出的字段 {list(data.keys())} 看起来是某个嵌套模型的字段，"
                f"但缺了顶层包装键。schema 期望顶层是 ``{expected_top}`` 之一，"
                f"请把你现在的数据包装进 ``{{'{expected_top[0]}': [...]}}`` 这种结构。"
            )
            continue
        # ===== Pydantic 校验 =====
        try:
            result = response_model.model_validate(data)
        except ValidationError as exc:
            issues = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()[:5]
            )
            feedback = f"数据形状不对（Pydantic 校验失败）：\n{issues}\n请按上述错误修。"
            continue
        # ===== 成功 =====
        return (
            result.model_dump_json(),
            response.usage.prompt_tokens if response.usage else None,
            output_tokens,
        )
    # 全部用尽
    raise ValueError(
        f"generate_structured_with_layer_b_async 耗尽 {max_retries + 1} 次尝试"
        + (f"；最后数据 last_data={last_data!r}" if last_data is not None else "")
        + (f"；最后反馈 {feedback}" if feedback else "")
    )
