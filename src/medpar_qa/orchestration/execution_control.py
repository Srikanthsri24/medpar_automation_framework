"""Opt-in execution observer: connected runs stop at the first failed validation."""
from contextlib import contextmanager
from contextvars import ContextVar

_observer = ContextVar('medpar_execution_observer', default=None)


class StageStopped(BaseException):
    """A business check stopped this stage, not an unexpected software exception."""


def observe(value):
    callback = _observer.get()
    if callback is not None:
        callback(value)


@contextmanager
def observing(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)
