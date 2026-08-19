"""Process-level fan-out of shutdown signals to in-flight attempts.

``dr_exec.forward_parent_signals`` cancels exactly one token, but a worker runs
several attempts concurrently. The registry owns one process token that the
signal handler cancels, and fans that cancellation out to every attempt token
registered at the time plus every token registered afterwards.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from dr_exec import CancelToken


class AttemptCancellationRegistry:
    """Tracks the cancel tokens of every in-flight attempt in this process."""

    def __init__(self) -> None:
        """Create an empty registry with a fresh process token."""
        self._lock = threading.Lock()
        self._tokens: set[CancelToken] = set()
        self._shutting_down = False
        self.process_token = CancelToken()

    @property
    def shutting_down(self) -> bool:
        """Whether a shutdown signal has been observed."""
        with self._lock:
            return self._shutting_down

    def cancel_all(self) -> None:
        """Cancel every registered token and every token registered later."""
        with self._lock:
            self._shutting_down = True
            tokens = tuple(self._tokens)
        self.process_token.cancel()
        for token in tokens:
            token.cancel()

    @contextmanager
    def attempt(self) -> Iterator[CancelToken]:
        """Yield a fresh attempt token bound to this process's lifetime.

        A token created after shutdown began starts already cancelled, so a
        late admission cannot outlive the drain.
        """
        token = CancelToken()
        with self._lock:
            already_shutting_down = self._shutting_down
            self._tokens.add(token)
        if already_shutting_down:
            token.cancel()
        try:
            yield token
        finally:
            with self._lock:
                self._tokens.discard(token)


@contextmanager
def forward_shutdown_signals(
    registry: AttemptCancellationRegistry,
) -> Iterator[None]:
    """Map SIGTERM and SIGINT to cancellation of every in-flight attempt.

    ``dr_exec.forward_parent_signals`` is main-thread-only, so this must be
    entered from the worker's main thread.
    """
    from dr_exec import forward_parent_signals

    watcher_stop = threading.Event()

    def watch() -> None:
        while not watcher_stop.wait(_WATCH_INTERVAL_SECONDS):
            if registry.process_token.cancelled:
                registry.cancel_all()
                return

    watcher = threading.Thread(target=watch, name="dr-exp-cancel-fanout", daemon=True)
    with forward_parent_signals(registry.process_token):
        watcher.start()
        try:
            yield
        finally:
            watcher_stop.set()
            watcher.join(timeout=_WATCH_JOIN_SECONDS)


#: How often the fan-out thread checks the process token. Cancellation latency
#: is dominated by DBOS's own poll interval, so a coarse tick is enough.
_WATCH_INTERVAL_SECONDS = 0.1
_WATCH_JOIN_SECONDS = 5.0

__all__ = ["AttemptCancellationRegistry", "forward_shutdown_signals"]
