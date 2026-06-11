from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def find_runtime_root(start: str | Path, required_relative_path: str | Path) -> Path:
    start_path = Path(start).resolve()
    required_path = Path(required_relative_path)

    for candidate in start_path.parents:
        if (candidate / required_path).exists():
            return candidate

    raise RuntimeError(
        f"Required runtime asset path '{required_path.as_posix()}' was not found from {start_path}"
    )