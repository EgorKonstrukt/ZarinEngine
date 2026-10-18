# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import sys
import threading
import time
import traceback
from collections import deque
from enum import IntEnum
from typing import Callable, Optional
from core.config.constants import LOGGER_MAX_ENTRIES
class LogLevel(IntEnum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
class LogEntry:
    __slots__ = ("level", "message", "timestamp", "traceback_str", "source", "thread_name")
    def __init__(self, level: LogLevel, message: str, tb: str = "", source: str = "", thread_name: str = ""):
        self.level = level
        self.message = message
        self.timestamp = time.time()
        self.traceback_str = tb
        self.source = source
        self.thread_name = thread_name if thread_name else threading.current_thread().name
    def formatted_time(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))
    def level_str(self) -> str:
        return LogLevel(self.level).name
    def to_dict(self) -> dict:
        return {"level": LogLevel(self.level).name, "message": self.message, "timestamp": self.timestamp, "time": self.formatted_time(), "traceback": self.traceback_str, "source": self.source, "thread": self.thread_name}
def _caller_source(skip: int = 3) -> str:
    try:
        frame = sys._getframe(skip)
    except Exception:
        return ""
    try:
        filename = os.path.basename(frame.f_code.co_filename or "")
        return filename + ":" + str(frame.f_lineno) + " " + str(frame.f_code.co_name)
    except Exception:
        return ""
    finally:
        del frame
def _format_exc(exc: Optional[BaseException]) -> str:
    if exc is None:
        return ""
    try:
        if exc.__traceback__ is not None:
            return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        active = sys.exc_info()
        if active[0] is not None:
            return traceback.format_exc()
        return str(type(exc).__name__) + ": " + str(exc)
    except Exception:
        try:
            return str(exc)
        except Exception:
            return ""
class Logger:
    _entries: deque = deque()
    _listeners: list[Callable[[LogEntry], None]] = []
    _max_entries: int = LOGGER_MAX_ENTRIES
    _min_level: LogLevel = LogLevel.DEBUG
    _lock: threading.RLock = threading.RLock()
    _file_path: str = ""
    _file_handle = None
    _file_writes: int = 0
    _max_file_bytes: int = 1048576
    @classmethod
    def add_listener(cls, fn: Callable[[LogEntry], None]):
        with cls._lock:
            cls._listeners.append(fn)
    @classmethod
    def remove_listener(cls, fn: Callable[[LogEntry], None]):
        with cls._lock:
            cls._listeners.remove(fn)
    @classmethod
    def set_level(cls, level: LogLevel):
        with cls._lock:
            cls._min_level = LogLevel(level)
    @classmethod
    def set_max_entries(cls, n: int):
        n = max(1, int(n))
        with cls._lock:
            cls._max_entries = n
            while len(cls._entries) > n:
                cls._entries.popleft()
    @classmethod
    def set_file(cls, path: str):
        with cls._lock:
            cls._close_file_locked()
            cls._file_path = str(path or "")
            cls._file_writes = 0
            if cls._file_path:
                try:
                    parent = os.path.dirname(os.path.abspath(cls._file_path))
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    cls._file_handle = open(cls._file_path, "a", encoding="utf-8", errors="replace")
                except Exception:
                    cls._file_handle = None
                    cls._file_path = ""
    @classmethod
    def get_file(cls) -> str:
        with cls._lock:
            return cls._file_path
    @classmethod
    def _close_file_locked(cls):
        try:
            handle = cls._file_handle
            cls._file_handle = None
            if handle is not None:
                try:
                    handle.flush()
                except Exception:
                    pass
                try:
                    handle.close()
                except Exception:
                    pass
        except Exception:
            pass
    @classmethod
    def _rotate_file_locked(cls):
        try:
            if not cls._file_path or cls._file_handle is None:
                return
            try:
                size = os.path.getsize(cls._file_path)
            except Exception:
                return
            if size < cls._max_file_bytes:
                return
            try:
                cls._file_handle.flush()
            except Exception:
                pass
            try:
                cls._file_handle.close()
            except Exception:
                pass
            try:
                backup = cls._file_path + ".1"
                try:
                    if os.path.exists(backup):
                        os.remove(backup)
                except Exception:
                    pass
                os.replace(cls._file_path, backup)
            except Exception:
                pass
            try:
                cls._file_handle = open(cls._file_path, "a", encoding="utf-8", errors="replace")
            except Exception:
                cls._file_handle = None
        except Exception:
            pass
    @classmethod
    def _write_file_locked(cls, entry: LogEntry):
        handle = cls._file_handle
        if handle is None:
            return
        try:
            line = entry.formatted_time() + " " + entry.level_str() + " [" + entry.thread_name + "] " + (entry.source + " " if entry.source else "") + entry.message + "\n"
            handle.write(line)
            if entry.traceback_str:
                handle.write(entry.traceback_str)
                if not entry.traceback_str.endswith("\n"):
                    handle.write("\n")
            cls._file_writes += 1
            if cls._file_writes >= 128:
                try:
                    handle.flush()
                except Exception:
                    pass
                cls._file_writes = 0
                cls._rotate_file_locked()
        except Exception:
            pass
    @classmethod
    def _emit(cls, entry: LogEntry):
        with cls._lock:
            cls._entries.append(entry)
            while len(cls._entries) > cls._max_entries:
                cls._entries.popleft()
            listeners = list(cls._listeners)
            cls._write_file_locked(entry)
        for fn in listeners:
            try:
                fn(entry)
            except Exception:
                pass
    @classmethod
    def _make(cls, level: LogLevel, msg: object, tb: str = "") -> LogEntry:
        try:
            text = str(msg)
        except Exception:
            text = ""
        return LogEntry(level, text, tb, _caller_source(), threading.current_thread().name)
    @classmethod
    def debug(cls, msg: object):
        if cls._min_level <= LogLevel.DEBUG:
            cls._emit(cls._make(LogLevel.DEBUG, msg))
    @classmethod
    def info(cls, msg: object):
        if cls._min_level <= LogLevel.INFO:
            cls._emit(cls._make(LogLevel.INFO, msg))
    @classmethod
    def warning(cls, msg: object):
        if cls._min_level <= LogLevel.WARNING:
            cls._emit(cls._make(LogLevel.WARNING, msg))
    @classmethod
    def error(cls, msg: object, exc: Optional[BaseException] = None):
        cls._emit(cls._make(LogLevel.ERROR, msg, _format_exc(exc)))
    @classmethod
    def get_entries(cls, min_level: Optional[LogLevel] = None) -> list[LogEntry]:
        with cls._lock:
            items = list(cls._entries)
        if min_level is None:
            return items
        try:
            threshold = LogLevel(min_level)
        except Exception:
            return items
        return [e for e in items if LogLevel(e.level) >= threshold]
    @classmethod
    def clear(cls):
        with cls._lock:
            cls._entries.clear()
