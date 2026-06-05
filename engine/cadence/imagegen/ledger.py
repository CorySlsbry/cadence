"""Persistent spend ledger — a hard cap so AI generation never exceeds budget.

Backed by a JSON file so the cap survives worker restarts and the autonomous
quality loop can't blow the budget across runs.
"""

from __future__ import annotations

import json
import os
import threading


class BudgetExceeded(Exception):
    """Raised when a charge would exceed the configured cap."""


class CostLedger:
    def __init__(self, path: str, cap_usd: float) -> None:
        self.path = path
        self.cap_usd = float(cap_usd)
        self._lock = threading.Lock()
        if not os.path.exists(path):
            self._write(0.0, 0)

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {"spent_usd": 0.0, "images": 0}

    def _write(self, spent: float, images: int) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"spent_usd": round(spent, 6), "images": images, "cap_usd": self.cap_usd}, fh)
        os.replace(tmp, self.path)

    def spent(self) -> float:
        return float(self._read().get("spent_usd", 0.0))

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent())

    def can_spend(self, cost: float) -> bool:
        return self.spent() + cost <= self.cap_usd + 1e-9

    def charge(self, cost: float) -> float:
        """Atomically record a charge; raise :class:`BudgetExceeded` if it would
        exceed the cap. Returns the new total spent."""
        with self._lock:
            data = self._read()
            spent = float(data.get("spent_usd", 0.0))
            if spent + cost > self.cap_usd + 1e-9:
                raise BudgetExceeded(
                    f"AI budget cap ${self.cap_usd:.2f} reached (spent ${spent:.2f}, "
                    f"need ${cost:.2f})."
                )
            new_spent = spent + cost
            self._write(new_spent, int(data.get("images", 0)) + 1)
            return new_spent
