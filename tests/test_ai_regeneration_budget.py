from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts.regenerate_reviewed_ai import Budget, BudgetError


def response(**kwargs):
    assert kwargs["max_output_tokens"] == 2048
    assert kwargs["store"] is False
    return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=20))


def test_budget_rejects_call_before_network_when_reserve_exceeds_cap(tmp_path):
    budget = Budget(tmp_path / "ledger.json", cap="0.001")
    called = []
    with pytest.raises(BudgetError, match="before a request"):
        budget.request(lambda **kwargs: called.append(kwargs), {"model": "gpt-5-mini", "input": "public research"})
    assert called == [] and budget.charged == 0


def test_confirmed_usage_releases_unused_reservation(tmp_path):
    budget = Budget(tmp_path / "ledger.json")
    budget.request(response, {"model": "gpt-5-mini", "input": "public research"})
    assert budget.charged == Decimal("0.0000425")
    assert budget.entries[0]["status"] == "usage_confirmed"


def test_uncertain_failure_retains_reservation_and_blocks_further_calls(tmp_path):
    budget = Budget(tmp_path / "ledger.json")
    calls = []
    def failure(**kwargs):
        calls.append(1)
        raise RuntimeError("simulated transport failure")
    with pytest.raises(BudgetError, match="reservation retained"):
        budget.request(failure, {"model": "gpt-5-mini", "input": "public research"})
    assert budget.charged > 0
    with pytest.raises(BudgetError, match="unconfirmed usage"):
        budget.request(failure, {"model": "gpt-5-mini", "input": "public research"})
    assert len(calls) == 1


def test_existing_ledger_cannot_be_reset_into_a_fresh_budget(tmp_path):
    path = tmp_path / "ledger.json"
    Budget(path)
    with pytest.raises(BudgetError, match="Existing ledger"):
        Budget(path)


def test_unreviewed_model_is_blocked_without_network(tmp_path):
    budget = Budget(tmp_path / "ledger.json")
    calls = []
    with pytest.raises(ValueError, match="pricing scope"):
        budget.request(lambda **kwargs: calls.append(1), {"model": "unreviewed-model", "input": ["research"]})
    assert calls == []
