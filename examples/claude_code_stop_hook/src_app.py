"""The app under test for the Stop-hook demo: a deliberately broken validator.

The agent claims the tests pass; this implementation makes
``test_email_requires_domain_dot`` fail, so the junit report shows 1 failure
and the Stop hook must block the claim.
"""

from __future__ import annotations

import re

# Known bug (intentional): no dot is required in the domain part.
_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def is_valid_email(address: str) -> bool:
    """Return True when ``address`` looks like an email (buggy: no domain dot)."""
    return bool(_ADDRESS_RE.match(address))
