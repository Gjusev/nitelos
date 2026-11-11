"""Tests for the demo app: one passes, one fails on purpose."""

from src_app import is_valid_email


def test_basic_address_passes() -> None:
    assert is_valid_email("alice@example.com")


def test_email_requires_domain_dot() -> None:
    assert not is_valid_email("bob@localhost")
