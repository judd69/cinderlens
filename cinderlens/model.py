"""Normalized profile-stats model and JSON snapshot save/load.

A snapshot is a plain-data record of one profiling run: per-function call
counts and timings plus run metadata.  Function identity is the
``file:lineno:name`` triple used by cProfile itself.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

from . import __version__

SNAPSHOT_FORMAT = 1


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )


class FunctionStats:
    """Timing data for one profiled function."""

    __slots__ = (
        "key",
        "file",
        "lineno",
        "name",
        "prim_calls",
        "calls",
        "tottime",
        "cumtime",
        "callers",
    )

    def __init__(
        self,
        key: str,
        file: str,
        lineno: int,
        name: str,
        prim_calls: int,
        calls: int,
        tottime: float,
        cumtime: float,
        callers: dict | None = None,
    ) -> None:
        self.key = key
        self.file = file
        self.lineno = lineno
        self.name = name
        self.prim_calls = prim_calls
        self.calls = calls
        self.tottime = tottime
        self.cumtime = cumtime
        # caller_key -> (prim_calls, calls, tottime, cumtime)
        self.callers = callers or {}

    @property
    def short(self) -> str:
        """Compact ``basename:lineno:name`` label for tables."""
        base = self.file if self.file in ("~", "") else os.path.basename(self.file)
        return f"{base}:{self.lineno}:{self.name}"

    @property
    def per_call(self) -> float:
        return self.tottime / self.calls if self.calls else 0.0

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "lineno": self.lineno,
            "name": self.name,
            "prim_calls": self.prim_calls,
            "calls": self.calls,
            "tottime": self.tottime,
            "cumtime": self.cumtime,
            "callers": {k: list(v) for k, v in self.callers.items()},
        }

    @classmethod
    def from_dict(cls, key: str, data: dict) -> "FunctionStats":
        return cls(
            key,
            data["file"],
            data["lineno"],
            data["name"],
            data["prim_calls"],
            data["calls"],
            data["tottime"],
            data["cumtime"],
            {k: tuple(v) for k, v in data.get("callers", {}).items()},
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FunctionStats)
            and self.key == other.key
            and self.to_dict() == other.to_dict()
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"FunctionStats({self.key!r}, calls={self.calls}, "
            f"tottime={self.tottime:.4f}, cumtime={self.cumtime:.4f})"
        )


class ProfileSnapshot:
    """One profiling run: metadata plus per-function stats."""

    def __init__(
        self,
        target: str,
        timestamp: str | None = None,
        python: str | None = None,
        total_time: float = 0.0,
        wall_time: float = 0.0,
        functions: dict[str, FunctionStats] | None = None,
    ) -> None:
        self.target = target
        self.timestamp = timestamp or _now_iso()
        self.python = python or sys.version.split()[0]
        self.total_time = total_time
        self.wall_time = wall_time
        self.functions = functions or {}
        # Run-local only (a target that raised mid-profile).  Not serialized.
        self.error: BaseException | None = None

    # -- derived facts ----------------------------------------------------
    def slowest_function(self) -> FunctionStats | None:
        if not self.functions:
            return None
        return max(self.functions.values(), key=lambda f: f.tottime)

    def slowest_module(self) -> tuple[str | None, float]:
        """(file path, total self-time) aggregated by file."""
        agg: dict[str, float] = {}
        for f in self.functions.values():
            agg[f.file] = agg.get(f.file, 0.0) + f.tottime
        if not agg:
            return None, 0.0
        path = max(agg, key=lambda p: agg[p])
        return path, agg[path]

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "cinderlens": SNAPSHOT_FORMAT,
            "version": __version__,
            "target": self.target,
            "timestamp": self.timestamp,
            "python": self.python,
            "total_time": self.total_time,
            "wall_time": self.wall_time,
            "functions": {k: f.to_dict() for k, f in self.functions.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ProfileSnapshot":
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError(f"not a valid CinderLens snapshot: {path}: {exc}")
        if not isinstance(data, dict) or data.get("cinderlens") != SNAPSHOT_FORMAT:
            raise ValueError(f"not a CinderLens snapshot (bad format marker): {path}")
        snap = cls(
            target=data.get("target", "?"),
            timestamp=data.get("timestamp"),
            python=data.get("python"),
            total_time=data.get("total_time", 0.0),
            wall_time=data.get("wall_time", 0.0),
        )
        funcs = data.get("functions", {})
        snap.functions = {
            key: FunctionStats.from_dict(key, fdata)
            for key, fdata in funcs.items()
        }
        return snap
