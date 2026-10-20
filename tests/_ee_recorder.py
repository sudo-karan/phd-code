"""A stand-in for Earth Engine that records every call the code under test makes.

Any attribute of a `Rec` is another `Rec`, and calling one appends a `Call` to the shared
log and returns a fresh `Rec`. Objects are compared by identity, so a test can ask whether
a call was given *that* image (`call.args == (kept,)`), and follow an image back to the call
that made it (`made_by`) and to the image that call was a method of (`owner_call`).

`call_log` turns a log into plain data (names and argument reprs), which is what the golden
files of tests/test_segmentation_off_golden.py and tests/test_clustering_off_golden.py hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(eq=False)
class Call:
    name: str  # dotted path of what was called, for reading
    owner: Any  # the object the method was called on (None for a module function)
    attr: str | None
    args: tuple
    kwargs: dict
    out: Any


class Rec:
    """Any Earth Engine object. An attribute is another Rec; calling one records the call.

    The shared log is kept as `_log`, not `log`, so that `.log()` (Earth Engine's natural
    logarithm, which the clustering stage takes of skewed bands) is recorded like any other
    call.
    """

    def __init__(self, name: str, log: list, owner: Rec | None = None, attr: str | None = None):
        self.name, self._log, self.owner, self.attr = name, log, owner, attr

    def __getattr__(self, attr: str) -> Rec:
        if attr.startswith("__"):
            raise AttributeError(attr)
        return Rec(f"{self.name}.{attr}", self._log, owner=self, attr=attr)

    def __call__(self, *args: Any, **kwargs: Any) -> Rec:
        out = Rec(f"{self.name}()", self._log)
        self._log.append(Call(self.name, self.owner, self.attr, args, kwargs, out))
        return out

    def __repr__(self) -> str:
        return f"<{self.name}>"


def calls(log: list, suffix: str) -> list[Call]:
    """Calls whose dotted name ends with `suffix`."""
    return [c for c in log if c.name.endswith(suffix)]


def made_by(log: list, obj: Rec) -> Call:
    """The call that returned `obj`."""
    (call,) = [c for c in log if c.out is obj]
    return call


def owner_call(log: list, call: Call) -> Call:
    """The call that made the object `call` was a method of."""
    return made_by(log, call.owner)


def _plain(value: Any) -> Any:
    if isinstance(value, Rec):
        return value.name
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in sorted(value.items())}
    if callable(value):
        # A function handed to a server-side map: its name, not its address, which
        # changes from run to run.
        return f"<function {value.__qualname__}>"
    return repr(value)


def call_log(log: list) -> list[list[Any]]:
    """[name, args, kwargs] per call, as plain JSON-able data."""
    return [[c.name, _plain(list(c.args)), _plain(c.kwargs)] for c in log]
