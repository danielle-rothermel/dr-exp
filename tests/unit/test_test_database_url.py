"""The integration suite's DSN guard shares dr-platform's helper."""

from __future__ import annotations

import pytest
from dr_platform.testing import validate_test_database_url

from tests.integration.conftest import (
    DATABASE_URL_ENV,
    DEFAULT_TEST_DATABASE_URL,
    test_database_url,
)

UNSAFE_DATABASE_URL = "postgresql+psycopg:///dr_exp"


def test_default_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    assert test_database_url() == DEFAULT_TEST_DATABASE_URL


def test_non_test_name_raises_the_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, UNSAFE_DATABASE_URL)
    monkeypatch.setattr(
        "tests.integration.conftest.create_engine",
        lambda *_args, **_kwargs: pytest.fail("create_engine must not run"),
    )

    with pytest.raises(ValueError, match="DR_PLATFORM_TEST_DATABASE_URL") as expected:
        validate_test_database_url(UNSAFE_DATABASE_URL)
    with pytest.raises(ValueError, match="ending in '_test'") as actual:
        test_database_url()

    assert type(actual.value) is type(expected.value)
    assert actual.value.args == expected.value.args
