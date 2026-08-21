"""The DBOS application version dr-exp pins for its workers.

Left to itself, DBOS computes an application version by hashing workflow
source, so any local edit yields a new version and orphans work enqueued by
the previous one. dr-exp instead pins the version explicitly -- through
``PlatformDbosConfig.application_version`` -- deriving it from the versions of
the packages whose code defines the wrapped workflows. Recovery is only
promised within one version, which is exactly the granularity these pins
express.

Because the pin derives from *distribution versions* rather than source, an
editable install holds one version across edits: a worker started after a stage
edit adopts PENDING attempts enqueued before it and runs them against the new
code. That follows directly from the choice above, and it is what development
wants -- versioning by source would instead mint a version per keystroke and
fail live work constantly. Bump a package version, or clear the queue, when a
stage-body change must not reach already-enqueued work.
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
