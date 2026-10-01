"""Budget guardrail evaluator and circuit-breaker logic."""

from typing import Optional

from costguard.config import (
    CURRENCY_SYMBOLS,
    EXIT_CODE_BUDGET_EXCEEDED,
    EXIT_CODE_SUCCESS,
)
from costguard.models import PolicyVerdict


def evaluate_budget_guardrail(
    net_monthly_impact: float,
    max_increase: Optional[float] = None,
    currency: str = "INR",
) -> PolicyVerdict:
    """Evaluate proposed plan against configured monthly budget ceiling.

    Rules:
    - If max_increase is None: No budget constraint set -> Always PASS.
    - If net_monthly_impact <= 0: Represents savings or neutral -> Always PASS.
    - If net_monthly_impact <= max_increase: Within budget threshold -> PASS (exit 0).
    - If net_monthly_impact > max_increase: Exceeds threshold -> FAIL (exit 1).

    Args:
        net_monthly_impact: Total net monthly delta from the plan.
        max_increase: User configured ceiling for monthly increase.
        currency: 3-letter currency code.

    Returns:
        PolicyVerdict with verdict status, formatted messages, and exit code.
    """
    symbol = CURRENCY_SYMBOLS.get(currency, "")

    if max_increase is None:
        return PolicyVerdict(
            budget_threshold=None,
            net_monthly_impact=net_monthly_impact,
            currency=currency,
            passed=True,
            status_label="PASSED",
            message="No budget threshold configured. Plan execution allowed.",
            exit_code=EXIT_CODE_SUCCESS,
        )

    # Net delta is within or equal to budget threshold
    if net_monthly_impact <= max_increase:
        return PolicyVerdict(
            budget_threshold=max_increase,
            net_monthly_impact=net_monthly_impact,
            currency=currency,
            passed=True,
            status_label="PASSED",
            message=(
                f"Net monthly increase of {symbol}{net_monthly_impact:,.2f} is within "
                f"allowed budget threshold of {symbol}{max_increase:,.2f}."
            ),
            exit_code=EXIT_CODE_SUCCESS,
        )

    # Threshold breached!
    overage = net_monthly_impact - max_increase
    return PolicyVerdict(
        budget_threshold=max_increase,
        net_monthly_impact=net_monthly_impact,
        currency=currency,
        passed=False,
        status_label="FAILED",
        message=(
            f"[CIRCUIT BREAKER] CostGuard: Budget threshold breached by {symbol}{overage:,.2f}/mo. "
            f"Deployment blocked."
        ),
        exit_code=EXIT_CODE_BUDGET_EXCEEDED,
    )
