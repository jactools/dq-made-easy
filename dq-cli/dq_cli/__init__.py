from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["main"]

if TYPE_CHECKING:
	from .run_plan import main as main


def __getattr__(name: str):
	if name == "main":
		from .run_plan import main as run_plan_main

		return run_plan_main
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")