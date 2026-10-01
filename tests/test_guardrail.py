"""Unit tests for the Budget Guardrail and Circuit Breaker policy."""

from costguard.config import (
    EXIT_CODE_BUDGET_EXCEEDED,
    EXIT_CODE_SUCCESS,
)
from costguard.policy.guardrail import evaluate_budget_guardrail


def test_guardrail_unconstrained():
    verdict = evaluate_budget_guardrail(net_monthly_impact=10000.0, max_increase=None)
    assert verdict.passed is True
    assert verdict.exit_code == EXIT_CODE_SUCCESS
    assert verdict.status_label == "PASSED"


def test_guardrail_below_threshold():
    verdict = evaluate_budget_guardrail(net_monthly_impact=3500.0, max_increase=5000.0, currency="INR")
    assert verdict.passed is True
    assert verdict.exit_code == EXIT_CODE_SUCCESS
    assert verdict.status_label == "PASSED"


def test_guardrail_equal_threshold():
    verdict = evaluate_budget_guardrail(net_monthly_impact=5000.0, max_increase=5000.0, currency="INR")
    assert verdict.passed is True
    assert verdict.exit_code == EXIT_CODE_SUCCESS
    assert verdict.status_label == "PASSED"


def test_guardrail_above_threshold():
    verdict = evaluate_budget_guardrail(net_monthly_impact=7500.0, max_increase=5000.0, currency="INR")
    assert verdict.passed is False
    assert verdict.exit_code == EXIT_CODE_BUDGET_EXCEEDED
    assert verdict.status_label == "FAILED"
    assert "Circuit Breaker" in verdict.message or "CIRCUIT BREAKER" in verdict.message


def test_guardrail_negative_impact_savings():
    # Savings should always pass, even if threshold is small
    verdict = evaluate_budget_guardrail(net_monthly_impact=-2500.0, max_increase=500.0, currency="INR")
    assert verdict.passed is True
    assert verdict.exit_code == EXIT_CODE_SUCCESS
    assert verdict.status_label == "PASSED"


def test_guardrail_zero_impact():
    verdict = evaluate_budget_guardrail(net_monthly_impact=0.0, max_increase=100.0, currency="INR")
    assert verdict.passed is True
    assert verdict.exit_code == EXIT_CODE_SUCCESS
