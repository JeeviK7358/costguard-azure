"""Unit tests for the Accounting and Monthly Cost Calculator."""

from unittest.mock import MagicMock

from costguard.accounting.calculator import (
    calculate_monthly_cost,
    calculate_plan_financials,
)
from costguard.config import HOURS_PER_MONTH
from costguard.models import ResourceChange
from costguard.pricing.engine import PricingEngine


def test_calculate_monthly_cost():
    # Exactly 730 hours
    assert HOURS_PER_MONTH == 730.0
    assert calculate_monthly_cost(10.0) == 7300.0
    assert calculate_monthly_cost(0.0) == 0.0
    assert calculate_monthly_cost(None) == 0.0
    assert calculate_monthly_cost(-5.0) == 0.0


def test_accounting_create_action():
    engine = MagicMock(spec=PricingEngine)
    engine.resolve_hourly_price.return_value = 5.0
    engine.get_stats.return_value = (0, 1, 1)

    change = ResourceChange(
        address="azurerm_linux_virtual_machine.app",
        resource_type="azurerm_linux_virtual_machine",
        actions=["create"],
        action_type="create",
        region="eastus",
        new_sku="Standard_B2s",
    )

    summary = calculate_plan_financials([change], engine, currency="INR")

    assert summary.prior_monthly_total == 0.0
    assert summary.projected_monthly_total == 3650.0  # 5.0 * 730
    assert summary.net_monthly_impact == 3650.0
    assert len(summary.resource_costs) == 1
    assert summary.resource_costs[0].delta == 3650.0


def test_accounting_delete_action():
    engine = MagicMock(spec=PricingEngine)
    engine.resolve_hourly_price.return_value = 4.0
    engine.get_stats.return_value = (1, 0, 0)

    change = ResourceChange(
        address="azurerm_linux_virtual_machine.old_vm",
        resource_type="azurerm_linux_virtual_machine",
        actions=["delete"],
        action_type="delete",
        region="eastus",
        old_sku="Standard_B1s",
    )

    summary = calculate_plan_financials([change], engine, currency="INR")

    assert summary.prior_monthly_total == 2920.0  # 4.0 * 730
    assert summary.projected_monthly_total == 0.0
    assert summary.net_monthly_impact == -2920.0  # Must be negative for savings
    assert summary.resource_costs[0].delta == -2920.0


def test_accounting_update_upgrade():
    engine = MagicMock(spec=PricingEngine)
    # Return 2.0 for old SKU, 5.0 for new SKU
    engine.resolve_hourly_price.side_effect = lambda sku, **kw: 2.0 if sku == "Standard_B1s" else 5.0
    engine.get_stats.return_value = (2, 0, 0)

    change = ResourceChange(
        address="azurerm_linux_virtual_machine.worker",
        resource_type="azurerm_linux_virtual_machine",
        actions=["update"],
        action_type="update",
        region="eastus",
        old_sku="Standard_B1s",
        new_sku="Standard_B2s",
    )

    summary = calculate_plan_financials([change], engine, currency="INR")

    old_cost = 2.0 * 730
    new_cost = 5.0 * 730
    expected_delta = new_cost - old_cost

    assert summary.prior_monthly_total == old_cost
    assert summary.projected_monthly_total == new_cost
    assert summary.net_monthly_impact == expected_delta
    assert summary.resource_costs[0].delta == expected_delta


def test_accounting_update_downgrade():
    engine = MagicMock(spec=PricingEngine)
    # Return 5.0 for old SKU, 2.0 for new SKU
    engine.resolve_hourly_price.side_effect = lambda sku, **kw: 5.0 if sku == "Standard_B2s" else 2.0
    engine.get_stats.return_value = (2, 0, 0)

    change = ResourceChange(
        address="azurerm_linux_virtual_machine.worker",
        resource_type="azurerm_linux_virtual_machine",
        actions=["update"],
        action_type="update",
        region="eastus",
        old_sku="Standard_B2s",
        new_sku="Standard_B1s",
    )

    summary = calculate_plan_financials([change], engine, currency="INR")

    assert summary.net_monthly_impact < 0
    assert summary.net_monthly_impact == (2.0 * 730) - (5.0 * 730)


def test_accounting_metadata_only_zero_cost():
    engine = MagicMock(spec=PricingEngine)
    engine.resolve_hourly_price.return_value = 3.0
    engine.get_stats.return_value = (1, 0, 0)

    change = ResourceChange(
        address="azurerm_linux_virtual_machine.tagged",
        resource_type="azurerm_linux_virtual_machine",
        actions=["update"],
        action_type="update",
        region="eastus",
        old_sku="Standard_B2s",
        new_sku="Standard_B2s",
        is_metadata_only=True,
    )

    summary = calculate_plan_financials([change], engine, currency="INR")

    assert summary.net_monthly_impact == 0.0
    assert summary.resource_costs[0].delta == 0.0
