"""Shared test configuration: ordinary tests run with network access denied (SEC-04 boundary)."""

from __future__ import annotations

import socket

import pytest


class NetworkAccessDenied(RuntimeError):
    """Raised when an ordinary offline test tries to open a network connection."""


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("github_live") is not None:
        return  # opt-in live marker: deselected by default, requires NITELOS_RUN_GITHUB_LIVE=1

    def deny(*_args: object, **_kwargs: object) -> None:
        raise NetworkAccessDenied("network access is disabled in offline tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
