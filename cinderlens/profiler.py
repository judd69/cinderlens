"""Run a target script under cProfile and normalize the results.

The target is executed with ``__name__ == "__main__"``, its own directory at
the front of ``sys.path``, and ``sys.argv`` set to ``[script, *script_args]`` —
the same environment ``python script.py args...`` would see.  Frames that
belong to CinderLens itself and to the frozen import machinery are filtered
out so the report only shows the target's world.
"""
from __future__ import annotations

import cProfile
import os
import pstats
import sys
import time

from .model import FunctionStats, ProfileSnapshot

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _excluded_filename(filename: str) -> bool:
    """Noise frames that never belong in a user's report."""
    if filename.startswith("<frozen"):
        return True
    # CinderLens' own frames (the exec driver lives in this package).
    if filename == _PACKAGE_DIR or filename.startswith(_PACKAGE_DIR + os.sep):
        return True
    return False


def snapshot_from_pstats(
    stats: dict,
    target: str,
    wall_time: float = 0.0,
) -> ProfileSnapshot:
    """Normalize a raw ``pstats`` stats-dict into a :class:`ProfileSnapshot`."""
    funcs: dict[str, FunctionStats] = {}
    for (fil, lineno, name), (cc, nc, tt, ct, callers) in stats.items():
        if _excluded_filename(fil):
            continue
        key = f"{fil}:{lineno}:{name}"
        caller_map: dict[str, tuple] = {}
        for (cfil, cln, cname), (ccc, ncc, ttt, cct) in callers.items():
            if _excluded_filename(cfil):
                continue
            caller_map[f"{cfil}:{cln}:{cname}"] = (ccc, ncc, ttt, cct)
        funcs[key] = FunctionStats(key, fil, lineno, name, cc, nc, tt, ct, caller_map)
    total = sum(entry[2] for entry in stats.values())
    return ProfileSnapshot(
        target=target, total_time=total, wall_time=wall_time, functions=funcs
    )


def profile_script(script: str, script_args: list[str] | tuple[str, ...] = ()) -> ProfileSnapshot:
    """Profile *script* with cProfile and return a normalized snapshot.

    If the target raises, the exception is captured on ``snapshot.error``
    (profiling is always stopped cleanly first) so the caller can still
    write a report from the partial data.
    """
    path = os.path.abspath(script)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"script not found: {script}")
    with open(path, "rb") as fh:
        code = compile(fh.read(), path, "exec")

    module_globals = {
        "__name__": "__main__",
        "__file__": path,
        "__builtins__": __builtins__,
        "__package__": None,
        "__spec__": None,
    }

    script_dir = os.path.dirname(path)
    old_argv = sys.argv
    path_added = script_dir not in sys.path
    sys.argv = [path, *script_args]
    if path_added:
        sys.path.insert(0, script_dir)

    profiler = cProfile.Profile()
    error: BaseException | None = None
    start = time.perf_counter()
    profiler.enable()
    try:
        exec(code, module_globals)
    except BaseException as exc:  # noqa: BLE001 - target errors must not kill the report
        error = exc
    finally:
        profiler.disable()
    wall_time = time.perf_counter() - start

    sys.argv = old_argv
    if path_added:
        try:
            sys.path.remove(script_dir)
        except ValueError:
            pass

    stats = pstats.Stats(profiler)
    snapshot = snapshot_from_pstats(stats.stats, target=script, wall_time=wall_time)
    snapshot.error = error
    return snapshot
