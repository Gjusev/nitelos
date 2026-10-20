"""API-01: the documented public API is importable (ADR-014 finding 1, NIT-017).

``from nitelos import *`` raised AttributeError because ``__all__`` listed
``Backend`` and ``BackendCapabilities`` without importing them. The fix is
additive: the names are imported at top level; nothing else changes.
"""

from __future__ import annotations

import subprocess
import sys

import nitelos


def test_api01_star_import_succeeds_in_subprocess() -> None:
    code = "from nitelos import *\n"
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_api01_every_all_name_resolves() -> None:
    for name in nitelos.__all__:
        assert getattr(nitelos, name, None) is not None, name


def test_api01_backend_names_come_from_backends() -> None:
    from nitelos.backends import Backend, BackendCapabilities

    assert nitelos.Backend is Backend
    assert nitelos.BackendCapabilities is BackendCapabilities
