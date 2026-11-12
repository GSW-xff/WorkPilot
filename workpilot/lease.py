"""Task-level leases with a monotonic fencing token.

Three ideas, each covering a failure the others cannot:

* **Lease** — a worker may advance a task only while it holds a time-boxed claim. If the
  process dies, the lease expires and another worker can take over instead of the task
  being stuck forever.
* **Heartbeat** — the holder renews the lease while it works, so "slow" is not mistaken
  for "dead" and a long external call does not hand the task to a second worker.
* **Fencing token** — every successful claim increments a counter. Renewal, release and
  the side-effect guard are all conditional on the token the worker was given, so a
  stalled worker that wakes up after being replaced can no longer write.

The keeper is deliberately small: a daemon thread renews the lease at one third of the
lease duration, and the executor calls :meth:`LeaseKeeper.check` immediately before any
external side effect.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from workpilot.models import utc_now

if TYPE_CHECKING:
    from workpilot.repository import TaskRepository

DEFAULT_LEASE_SECONDS = 15.0


class LeaseLost(RuntimeError):
    """Raised when this worker no longer owns the task lease.

    The worker must stop immediately and must not write a terminal state: whoever owns
    the newer fence token is now responsible for reconciling the task.
    """


@dataclass(frozen=True)
class TaskLease:
    tenant_id: str
    task_id: str
    owner: str
    fence_token: int
    expires_at: datetime


def lease_interval(lease_seconds: float) -> float:
    """Renew at a third of the lease: two consecutive renewal failures still fit."""
    return max(0.05, lease_seconds / 3)


class LeaseKeeper:
    """Renews a task lease in the background and fails closed once it is lost."""

    def __init__(
        self,
        repository: TaskRepository,
        lease: TaskLease,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        interval: float | None = None,
        on_renew: Callable[[], None] | None = None,
    ) -> None:
        self.repository = repository
        self.lease = lease
        self.lease_seconds = lease_seconds
        self.interval = interval if interval is not None else lease_interval(lease_seconds)
        self.on_renew = on_renew
        self.lost = False
        self.renewals = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def fence_token(self) -> int:
        return self.lease.fence_token

    def renew_once(self) -> bool:
        renewed = self.repository.renew_lease(
            self.lease.tenant_id,
            self.lease.task_id,
            self.lease.owner,
            self.lease.fence_token,
            self.lease_seconds,
        )
        if renewed:
            self.renewals += 1
            if self.on_renew is not None:
                self.on_renew()
            return True
        self.lost = True
        return False

    def check(self) -> None:
        """Fail closed unless this worker still owns a live lease."""
        if not self.lost and self.repository.owns_lease(
            self.lease.tenant_id,
            self.lease.task_id,
            self.lease.owner,
            self.lease.fence_token,
        ):
            return
        self.lost = True
        raise LeaseLost(
            f"lease lost for task {self.lease.task_id}: fence token "
            f"{self.lease.fence_token} is stale"
        )

    def start(self) -> LeaseKeeper:
        self._thread = threading.Thread(
            target=self._loop,
            name=f"lease-heartbeat-{self.lease.task_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            if not self.renew_once():
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.interval * 2))
        self._thread = None

    def __enter__(self) -> LeaseKeeper:
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def snapshot(self) -> dict[str, object]:
        return {
            "owner": self.lease.owner,
            "fence_token": self.lease.fence_token,
            "renewals": self.renewals,
            "lost": self.lost,
            "checked_at": utc_now().isoformat(),
        }
