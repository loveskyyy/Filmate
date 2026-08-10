"""
Lightweight project change hint bus used by the workspace realtime layer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from typing import Any, Literal

logger = logging.getLogger(__name__)

ProjectChangeSource = Literal["webui", "worker", "filesystem"]
ProjectChangeListener = Callable[[str, ProjectChangeSource, tuple[str, ...]], None]
ProjectChangeBatch = dict[str, Any]
ProjectChangeBatchListener = Callable[
    [str, ProjectChangeSource, tuple[ProjectChangeBatch, ...]],
    None,
]
# 专供 save_script 的高优先级通道：sub-agent 写完剧本后希望前端毫秒级收到，
# 走 ``_listeners`` 的 0.5s 轮询等待太慢。这里用一条独立 listener 链做立即广播。
ScriptSavedListener = Callable[[str, str, int | None], None]

_current_source: ContextVar[ProjectChangeSource] = ContextVar(
    "project_change_source",
    default="filesystem",
)
_listeners: list[ProjectChangeListener] = []
_batch_listeners: list[ProjectChangeBatchListener] = []
_script_saved_listeners: list[ScriptSavedListener] = []
_listeners_lock = RLock()


def get_project_change_source() -> ProjectChangeSource:
    """Return the current source label for project mutations."""
    return _current_source.get()


@contextmanager
def project_change_source(source: ProjectChangeSource):
    """Temporarily tag project mutations with a source label."""
    token = _current_source.set(source)
    try:
        yield
    finally:
        _current_source.reset(token)


def emit_project_change_hint(
    project_name: str,
    source: ProjectChangeSource | None = None,
    changed_paths: Iterable[str] | None = None,
) -> None:
    """Notify listeners that project files were just written."""
    resolved_source = source or get_project_change_source()
    paths = tuple(dict.fromkeys(str(path) for path in (changed_paths or ())))
    with _listeners_lock:
        listeners = list(_listeners)

    for listener in listeners:
        try:
            listener(project_name, resolved_source, paths)
        except Exception:
            logger.exception("项目变更 hint listener 执行失败")


def register_project_change_listener(
    listener: ProjectChangeListener,
) -> Callable[[], None]:
    """Register a listener. Returns an unregister callback."""
    with _listeners_lock:
        _listeners.append(listener)

    def unregister() -> None:
        with _listeners_lock:
            try:
                _listeners.remove(listener)
            except ValueError:
                return

    return unregister


def emit_project_change_batch(
    project_name: str,
    changes: Iterable[ProjectChangeBatch],
    source: ProjectChangeSource | None = None,
) -> None:
    """Notify listeners with a ready-to-broadcast project change batch."""
    resolved_source = source or get_project_change_source()
    payload = tuple(dict(change) for change in changes if isinstance(change, dict))
    if not payload:
        return

    with _listeners_lock:
        listeners = list(_batch_listeners)

    for listener in listeners:
        try:
            listener(project_name, resolved_source, payload)
        except Exception:
            logger.exception("项目变更 batch listener 执行失败")


def register_project_change_batch_listener(
    listener: ProjectChangeBatchListener,
) -> Callable[[], None]:
    """Register a batch listener. Returns an unregister callback."""
    with _listeners_lock:
        _batch_listeners.append(listener)

    def unregister() -> None:
        with _listeners_lock:
            try:
                _batch_listeners.remove(listener)
            except ValueError:
                return

    return unregister


def emit_script_saved_hint(
    project_name: str,
    script_filename: str,
    episode: int | None,
) -> None:
    """立即广播"剧本已保存"事件，绕过 project_change_hint 的 0.5s 轮询等待。

    由 :func:`lib.project_manager.ProjectManager._write_script_unlocked` 在
    写盘之后、同步 project.json 之前调用；前端订阅者在毫秒级拿到 ``script_saved``
    事件，能立刻刷新项目状态并弹"第 N 集剧本已生成"通知，不再依赖
    :class:`server.services.project_events.ProjectEventService` 的
    watch task 轮询触发。
    """
    with _listeners_lock:
        listeners = list(_script_saved_listeners)

    for listener in listeners:
        try:
            listener(project_name, script_filename, episode)
        except Exception:
            logger.exception("script_saved listener 执行失败")


def register_script_saved_listener(
    listener: ScriptSavedListener,
) -> Callable[[], None]:
    """Register a script_saved listener. Returns an unregister callback."""
    with _listeners_lock:
        _script_saved_listeners.append(listener)

    def unregister() -> None:
        with _listeners_lock:
            try:
                _script_saved_listeners.remove(listener)
            except ValueError:
                return

    return unregister
