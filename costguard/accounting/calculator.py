"""Monthly cost and delta calculation engine."""

from typing import List, Optional

from costguard.config import HOURS_PER_MONTH
from costguard.models import FinancialSummary, ResourceChange, ResourceCost
from costguard.pricing.engine import PricingEngine


def calculate_monthly_cost(hourly_rate: Optional[float]) -> float:
    """Calculate standard monthly cost from an hourly rate using 730 hours/month."""
    if hourly_rate is None or hourly_rate < 0:
        return 0.0
    return round(hourly_rate * HOURS_PER_MONTH, 4)


def calculate_plan_financials(
    changes: List[ResourceChange],
    pricing_engine: PricingEngine,
    currency: str = "INR",
) -> FinancialSummary:
    """Calculate financial impact for all resources in a parsed Terraform plan.

    Implements the Terraform action matrix:
    - CREATE: old = 0, new = calculated, delta = +new
    - DELETE: old = calculated, new = 0, delta = -old (negative delta)
    - UPDATE: old = old calculated, new = new calculated, delta = new - old
    - REPLACE: old = old calculated, new = new calculated, delta = new - old
    - NO-OP: old = old, new = old, delta = 0

    Args:
        changes: List of parsed ResourceChange objects.
        pricing_engine: Instantiated PricingEngine.
        currency: 3-letter currency code.

    Returns:
        FinancialSummary with individual ResourceCost records and aggregated totals.
    """
    resource_costs: List[ResourceCost] = []
    skipped_resources: List[str] = []
    warnings: List[str] = []

    for change in changes:
        if not change.is_billable:
            skipped_resources.append(f"{change.address} ({change.skip_reason or 'non-billable'})")
            continue

        # Handle metadata-only updates (e.g. tag changes, description updates)
        if change.is_metadata_only:
            # Look up price for current SKU so report shows actual baseline and new cost
            current_rate = pricing_engine.resolve_hourly_price(
                sku=change.new_sku or change.old_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            ) or 0.0
            monthly = calculate_monthly_cost(current_rate)

            resource_costs.append(
                ResourceCost(
                    address=change.address,
                    resource_type=change.resource_type,
                    action=change.action_type.upper(),
                    region=change.region,
                    old_sku=change.old_sku,
                    new_sku=change.new_sku,
                    old_hourly_rate=current_rate,
                    new_hourly_rate=current_rate,
                    old_monthly_cost=monthly,
                    new_monthly_cost=monthly,
                    delta=0.0,
                    currency=currency,
                )
            )
            continue

        old_hourly = 0.0
        new_hourly = 0.0
        item_warning: Optional[str] = None

        if change.action_type == "create":
            new_rate = pricing_engine.resolve_hourly_price(
                sku=change.new_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            )
            if new_rate is None:
                item_warning = f"Missing price for SKU '{change.new_sku}'"
                warnings.append(f"{change.address}: {item_warning}")
            new_hourly = new_rate or 0.0
            old_hourly = 0.0

        elif change.action_type == "delete":
            old_rate = pricing_engine.resolve_hourly_price(
                sku=change.old_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            )
            if old_rate is None:
                item_warning = f"Missing price for SKU '{change.old_sku}'"
                warnings.append(f"{change.address}: {item_warning}")
            old_hourly = old_rate or 0.0
            new_hourly = 0.0

        elif change.action_type in ("update", "replace"):
            old_rate = pricing_engine.resolve_hourly_price(
                sku=change.old_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            )
            new_rate = pricing_engine.resolve_hourly_price(
                sku=change.new_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            )
            if old_rate is None:
                warnings.append(f"{change.address}: Missing prior price for SKU '{change.old_sku}'")
            if new_rate is None:
                warnings.append(f"{change.address}: Missing new price for SKU '{change.new_sku}'")
            old_hourly = old_rate or 0.0
            new_hourly = new_rate or 0.0

        elif change.action_type == "no-op":
            existing_rate = pricing_engine.resolve_hourly_price(
                sku=change.new_sku or change.old_sku,
                region=change.region,
                currency=currency,
                resource_type=change.resource_type,
                extra_attributes=change.extra_attributes,
            ) or 0.0
            old_hourly = existing_rate
            new_hourly = existing_rate

        old_monthly = calculate_monthly_cost(old_hourly)
        new_monthly = calculate_monthly_cost(new_hourly)
        delta = round(new_monthly - old_monthly, 2)

        resource_costs.append(
            ResourceCost(
                address=change.address,
                resource_type=change.resource_type,
                action=change.action_type.upper(),
                region=change.region,
                old_sku=change.old_sku,
                new_sku=change.new_sku,
                old_hourly_rate=old_hourly,
                new_hourly_rate=new_hourly,
                old_monthly_cost=round(old_monthly, 2),
                new_monthly_cost=round(new_monthly, 2),
                delta=delta,
                currency=currency,
                warning=item_warning,
            )
        )

    # Compute aggregates
    prior_total = round(sum(r.old_monthly_cost for r in resource_costs), 2)
    projected_total = round(sum(r.new_monthly_cost for r in resource_costs), 2)
    net_monthly_impact = round(sum(r.delta for r in resource_costs), 2)

    hits, misses, api_calls = pricing_engine.get_stats()

    return FinancialSummary(
        prior_monthly_total=prior_total,
        projected_monthly_total=projected_total,
        net_monthly_impact=net_monthly_impact,
        currency=currency,
        cache_hits=hits,
        cache_misses=misses,
        api_calls=api_calls,
        resource_costs=resource_costs,
        skipped_resources=skipped_resources,
        warnings=warnings,
    )
