"""The DBOS application version dr-exp pins for its workers.

DBOS computes an application version by hashing workflow source, but only
inside ``DBOS.launch()``. dr-platform needs that version *before* launch, when
``register_scheduled_dispatcher`` builds the ``LiveDbosIdentity`` its sweep
compares against: an identity built from the pre-launch empty string makes the
sweep read every live attempt as ``stale_app_version`` and fail it.

So dr-exp pins the version itself, derived from the versions of the three
packages whose code defines the wrapped workflows. Recovery is only promised
within one version, which is exactly the granularity these pins express.
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
