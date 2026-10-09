"""Turn unexpected filesystem errors into `IO_ERROR` at every public entry point."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from . import errors as E
from .errors import MultiAccountError
from .fs import FsError

_P = ParamSpec("_P")
_R = TypeVar("_R")


def io_errors(fn: Callable[_P, _R]) -> Callable[_P, _R]:
    """Decorator: a raw `FsError` escaping `fn` becomes `MultiAccountError(IO_ERROR, path=...)`."""

    @wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return fn(*args, **kwargs)
        except FsError as e:
            raise MultiAccountError(E.IO_ERROR, f"unexpected filesystem error {e.code}", e.path) from e

    return wrapper
