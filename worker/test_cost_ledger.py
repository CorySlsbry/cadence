"""Unit tests for SupabaseCostLedger per-user token metering + the global cap.

Pure logic: a fake Supabase client records rpc calls and returns canned rows, so no
database or network is touched. Verifies the multi-tenant contract:
  - BYOK-style ledger (user_id=None) charges the global cap only, never a user token.
  - A metered user burns exactly one token per image (atomic spend_tokens) + the cap.
  - Out of tokens -> can_spend() is False (pre-flight) and charge() raises BudgetExceeded
    WITHOUT charging the global cap (the user couldn't pay, so nothing is recorded).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cadence.imagegen.ledger import BudgetExceeded  # noqa: E402
from cadence_worker import SupabaseCostLedger  # noqa: E402


class _Resp:
    def __init__(self, data):
        self.data = data


class _TableQuery:
    def __init__(self, data):
        self._d = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return _Resp(self._d)


class _RpcCall:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return _Resp(self._fn())


class FakeSupabase:
    """Minimal stand-in for the supabase Client surface the ledger touches."""

    def __init__(self, tokens=None, spent=0.0, spend_raises=False, charge_raises=False):
        self.tokens = tokens
        self.spent_usd = spent
        self.spend_raises = spend_raises
        self.charge_raises = charge_raises
        self.spend_calls: list[dict] = []
        self.charge_calls: list[dict] = []

    def table(self, name):
        if name == "profiles":
            return _TableQuery([{"tokens": self.tokens}] if self.tokens is not None else [])
        return _TableQuery([{"spent_usd": self.spent_usd, "id": 1}])

    def rpc(self, name, params):
        if name == "spend_tokens":
            def burn():
                self.spend_calls.append(params)
                if self.spend_raises:
                    raise RuntimeError("insufficient_tokens")
                self.tokens -= params["p_n"]
                return self.tokens
            return _RpcCall(burn)

        def charge():
            self.charge_calls.append(params)
            if self.charge_raises:
                raise RuntimeError("AI budget cap reached")
            self.spent_usd += params["p_cost"]
            return self.spent_usd
        return _RpcCall(charge)


COST = 0.05
CAP = 1000.0


def test_byok_ledger_charges_global_cap_only_never_a_user_token():
    fake = FakeSupabase(spent=0.0)
    ledger = SupabaseCostLedger(fake, cap_usd=CAP, user_id=None)

    assert ledger.can_spend(COST) is True
    ledger.charge(COST)

    assert fake.spend_calls == []  # no per-user metering when user_id is None
    assert fake.charge_calls == [{"p_cost": COST, "p_cap": CAP}]


def test_metered_user_burns_exactly_one_token_per_image_plus_global_cap():
    fake = FakeSupabase(tokens=3, spent=0.0)
    ledger = SupabaseCostLedger(fake, cap_usd=CAP, user_id="u1", job_id="j1")

    assert ledger.can_spend(COST) is True
    ledger.charge(COST)

    assert fake.spend_calls == [{"p_user": "u1", "p_n": 1, "p_job": "j1"}]
    assert fake.tokens == 2
    assert fake.charge_calls == [{"p_cost": COST, "p_cap": CAP}]


def test_zero_tokens_fails_preflight_can_spend():
    fake = FakeSupabase(tokens=0, spent=0.0)
    ledger = SupabaseCostLedger(fake, cap_usd=CAP, user_id="u1")

    assert ledger.can_spend(COST) is False


def test_out_of_tokens_charge_raises_and_skips_global_cap():
    fake = FakeSupabase(tokens=1, spend_raises=True, spent=0.0)
    ledger = SupabaseCostLedger(fake, cap_usd=CAP, user_id="u1", job_id="j1")

    with pytest.raises(BudgetExceeded):
        ledger.charge(COST)

    assert fake.charge_calls == []  # user couldn't pay -> global cap untouched


def test_unreadable_token_balance_fails_closed():
    # profiles row missing -> 0 tokens -> treated as "no tokens", AI stops (fail closed).
    fake = FakeSupabase(tokens=None, spent=0.0)
    ledger = SupabaseCostLedger(fake, cap_usd=CAP, user_id="u1")

    assert ledger.can_spend(COST) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
