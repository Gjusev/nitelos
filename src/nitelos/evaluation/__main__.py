"""CLI entry point: ``python -m nitelos.evaluation run ...`` (NIT-012).

Exit codes (doc 12): 0 for a complete run regardless of model accuracy; 2 for an
invalid manifest or configuration; 3 for an infrastructure failure or incomplete
run. The smolvlm backend requires NIT-008 and the ``local`` extra; until then the
CLI fails with exit 2 and an actionable message — a model run is never faked.
"""

from __future__ import annotations

from nitelos.evaluation.runner import main

raise SystemExit(main())
