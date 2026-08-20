"""The DBOS application version dr-exp pins for its workers.

Left to itself, DBOS computes an application version by hashing workflow
source, so any local edit yields a new version and orphans work enqueued by
the previous one. dr-exp instead pins the version explicitly -- through
``PlatformDbosConfig.application_version`` -- deriving it from the versions of
the packages whose code defines the wrapped workflows. Recovery is only
promised within one version, which is exactly the granularity these pins
express.

Limitation: this hashes *distribution versions*, not source. Editing dr-exp's
own stage code in an editable install leaves the version unchanged, so a
worker started after the edit will adopt PENDING attempts enqueued before it
and run them against the new code. That is the right default for development,
where the alternative -- a new version on every keystroke -- would fail live
work constantly. Bump the version, or clear the queue, when a stage-body change
must not be applied to already-enqueued work.
"""

from __future__ import annotations

import hashlib
from functools import cache
from importlib.metadata import PackageNotFoundError, version

#: Packages whose code determines the shape of a wrapped stage workflow.
VERSIONED_PACKAGES = ("dr-exp", "dr-platform", "dr-exec", "dbos")

#: Length of the rendered version. DBOS stores it as a plain string.
_VERSION_LENGTH = 16


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:  # pragma: no cover -- editable installs only
        return "unknown"


@cache
def application_version() -> str:
    """Return this installation's stable DBOS application version."""
    identity = "\0".join(
        f"{name}={_package_version(name)}" for name in VERSIONED_PACKAGES
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"dr-exp-{digest[:_VERSION_LENGTH]}"


__all__ = ["VERSIONED_PACKAGES", "application_version"]
