"""AI image generation for contextual b-roll (ports-and-adapters).

The core pipeline depends only on the :class:`ImageGenerator` port, so it is fully
testable with the free :class:`StubGenerator` and switches to a real provider
(Ideogram v3) by config. A :class:`CostLedger` hard-caps spend so the autonomous
quality loop can never exceed the user's budget.
"""

from __future__ import annotations

from cadence.imagegen.base import GenResult, ImageGenerator
from cadence.imagegen.ledger import BudgetExceeded, CostLedger
from cadence.imagegen.stub import StubGenerator

__all__ = ["GenResult", "ImageGenerator", "CostLedger", "BudgetExceeded", "StubGenerator"]
