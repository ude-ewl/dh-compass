"""Cooperative progress and cancellation primitives for application runs.

The optimization pipeline is deliberately independent from the web package.  A
caller can provide an observer that translates these events to a log, a CLI
progress display, or persisted web job events.  The default observer is a
no-op, so existing command-line and library callers retain their behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Protocol, runtime_checkable


class CancellationRequested(RuntimeError):
    """Raised at a safe cooperative cancellation point."""


class CancellationToken:
    """A small cancellation token that can also wrap a process event.

    Cancellation is intentionally cooperative.  It is checked between pipeline
    stages and candidate evaluations; an already-running solver call is not
    forcibly interrupted because doing so can leave solver state and temporary
    files in an unsafe condition.
    """

    def __init__(self, event: Any | None = None) -> None:
        self._event = event if event is not None else Event()

    @classmethod
    def from_event(cls, event: Any) -> "CancellationToken":
        return cls(event)

    def cancel(self) -> None:
        setter = getattr(self._event, "set", None)
        if callable(setter):
            setter()

    @property
    def cancelled(self) -> bool:
        return self.is_cancelled()

    def is_cancelled(self) -> bool:
        checker = getattr(self._event, "is_set", None)
        return bool(checker()) if callable(checker) else False

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancellationRequested("Cancellation was requested.")


# A name that describes the wrapped implementation is useful to worker code
# and keeps callers from depending on the backing threading/multiprocessing
# event type.
CooperativeCancellationToken = CancellationToken


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One observer notification with JSON-friendly event data."""

    event_type: str
    data: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class PipelineObserver(Protocol):
    """Protocol implemented by consumers of pipeline progress events.

    ``emit`` is the canonical low-level method.  The pipeline also accepts
    observers exposing named methods such as ``stage_started`` through the
    :func:`emit_progress` compatibility adapter, which is convenient for
    small tests and library integrations.
    """

    def emit(
        self, event_type: str, data: Mapping[str, Any] | None = None
    ) -> None:
        """Receive one event without changing pipeline control flow."""


class NullPipelineObserver:
    """Default no-op observer used when no progress consumer is supplied."""

    def emit(
        self, event_type: str, data: Mapping[str, Any] | None = None
    ) -> None:
        return None


_NOOP_OBSERVER = NullPipelineObserver()

_EVENT_METHODS = {
    "pipeline.stage_started": "stage_started",
    "pipeline.stage_completed": "stage_completed",
    "pipeline.stage_failed": "stage_failed",
    "optimization.candidate_started": "candidate_started",
    "optimization.candidate_completed": "candidate_completed",
    "optimization.candidate_failed": "candidate_failed",
    "job.warning": "warning",
    "heartbeat": "heartbeat",
}


def emit_progress(
    observer: PipelineObserver | Any | None,
    event_type: str,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Deliver an event to any supported observer shape.

    Observer failures are deliberately allowed to propagate.  A web worker can
    then mark the run failed instead of silently reporting a successful run
    whose progress store was unavailable.  The no-op path is allocation-free
    for ordinary CLI calls.
    """

    if observer is None or observer is _NOOP_OBSERVER:
        return
    payload = dict(data or {})
    emit = getattr(observer, "emit", None)
    if callable(emit):
        emit(event_type, payload)
        return
    on_event = getattr(observer, "on_event", None)
    if callable(on_event):
        on_event(ProgressEvent(event_type=event_type, data=payload))
        return
    method_name = _EVENT_METHODS.get(event_type)
    method = getattr(observer, method_name, None) if method_name else None
    if callable(method):
        try:
            method(**payload)
        except TypeError:
            # A minimal observer often accepts the whole payload as one value.
            method(payload)


def check_cancellation(token: Any | None) -> None:
    """Check a token or event supplied by an application boundary."""

    if token is None:
        return
    raise_if_cancelled = getattr(token, "raise_if_cancelled", None)
    if callable(raise_if_cancelled):
        raise_if_cancelled()
        return
    checker = getattr(token, "is_cancelled", None)
    if callable(checker) and checker():
        raise CancellationRequested("Cancellation was requested.")
    checker = getattr(token, "is_set", None)
    if callable(checker) and checker():
        raise CancellationRequested("Cancellation was requested.")
    if bool(getattr(token, "cancelled", False)):
        raise CancellationRequested("Cancellation was requested.")


def no_op_observer() -> PipelineObserver:
    """Return the shared no-op observer for explicit dependency injection."""

    return _NOOP_OBSERVER


__all__ = [
    "CancellationRequested",
    "CancellationToken",
    "CooperativeCancellationToken",
    "NullPipelineObserver",
    "PipelineObserver",
    "ProgressEvent",
    "check_cancellation",
    "emit_progress",
    "no_op_observer",
]
