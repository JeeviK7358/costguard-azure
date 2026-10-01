"""Clean, beginner-friendly terminal presentation for CostGuard."""

import json
from typing import Optional

from costguard.config import CURRENCY_SYMBOLS
from costguard.models import FinancialSummary, PolicyVerdict


def format_money(amount: float, symbol: str = "₹", show_sign: bool = False) -> str:
    """Format an amount into a simple, clean currency string (e.g. ₹3,200 or ₹2,915.04)."""
    abs_amt = abs(amount)
    if abs_amt == 0:
        val_str = f"{symbol}0"
    elif abs_amt % 1 == 0:
        val_str = f"{symbol}{int(abs_amt):,}"
    else:
        val_str = f"{symbol}{abs_amt:,.2f}"

    if amount > 0:
        return f"+{val_str}" if show_sign else val_str
    elif amount < 0:
        return f"-{val_str}"
    else:
        return val_str


def format_resource_name(address: str, res_type: str = "") -> str:
    """Generate simple, clean resource labels (e.g. vm.app, disk.data)."""
    if address.startswith("vm.") or address.startswith("disk.") or address.startswith("VM.") or address.startswith("Disk."):
        return address.lower()

    parts = address.split(".")
    name = parts[-1] if len(parts) > 1 else address
    prefix = parts[0] if len(parts) > 1 else res_type

    if "virtual_machine" in prefix or "virtual_machine" in res_type:
        return f"vm.{name}"
    if "managed_disk" in prefix or "managed_disk" in res_type:
        return f"disk.{name}"
    return name.lower()


def print_cost_report(
    summary: FinancialSummary,
    verdict: PolicyVerdict,
    verbose: bool = False,
    show_progress: bool = True,
    **kwargs,
) -> None:
    """Print beginner-friendly, clean CostGuard output."""
    symbol = CURRENCY_SYMBOLS.get(summary.currency, "₹")
    sep = "────────────────────────────────────────────────────────"

    print("========================================================")
    print("COSTGUARD — COST IMPACT REPORT")
    print("==============================")
    print()

    # Step progress indicators
    if show_progress:
        print("✓ Terraform plan loaded")
        print("✓ Changes analyzed")
        print("✓ Azure pricing checked")
        print("✓ Cost calculated")
        print()

    # Case 1: No billable resources
    if not summary.resource_costs:
        print("No billable changes detected.")
        print()
        print(f"Monthly Change: {symbol}0.00")
        print()
        print("✓ WITHIN BUDGET")

        if verbose and summary.skipped_resources:
            print()
            print("DETAILS")
            print("────────────────────────")
            print(f"Skipped:\n  {len(summary.skipped_resources)} non-billable resources")
        return

    # Case 2: Billable comparison table
    res_col = 16
    act_col = 10
    cost_col = 14

    for r in summary.resource_costs:
        name = format_resource_name(r.address, r.resource_type)
        res_col = max(res_col, len(name) + 2)

    header = f"{'Resource':<{res_col}}{'Action':<{act_col}}{'Current':<{cost_col}}{'Projected':<{cost_col}}{'Impact'}"
    print(header)
    print(sep)

    for r in summary.resource_costs:
        name = format_resource_name(r.address, r.resource_type)
        action = "UPDATE" if r.action in ("UPDATE", "REPLACE") else r.action
        curr_str = format_money(r.old_monthly_cost, symbol=symbol)
        proj_str = format_money(r.new_monthly_cost, symbol=symbol)
        impact_str = format_money(r.delta, symbol=symbol, show_sign=True)

        print(f"{name:<{res_col}}{action:<{act_col}}{curr_str:<{cost_col}}{proj_str:<{cost_col}}{impact_str}")

    print()
    print(sep)

    # Monthly & Annual Summary Section
    curr_tot = format_money(summary.prior_monthly_total, symbol=symbol)
    proj_tot = format_money(summary.projected_monthly_total, symbol=symbol)
    monthly_impact = format_money(summary.net_monthly_impact, symbol=symbol, show_sign=True)
    annual_impact = format_money(summary.net_monthly_impact * 12.0, symbol=symbol, show_sign=True)

    print(f"{'CURRENT COST':<18} {curr_tot}/month")
    print(f"{'PROJECTED COST':<18} {proj_tot}/month")
    print(f"{'MONTHLY IMPACT':<18} {monthly_impact}/month")
    print(f"{'ANNUAL IMPACT':<18} {annual_impact}/year")
    print()

    if verdict.budget_threshold is not None:
        budget_str = format_money(verdict.budget_threshold, symbol=symbol)
        print(f"{'BUDGET':<18} {budget_str}/month")

    # Final Verdict Section
    if verdict.passed:
        print(f"{'STATUS':<18} ✓ WITHIN BUDGET")
        print()
        print("DEPLOYMENT APPROVED")
    else:
        print(f"{'STATUS':<18} ✕ EXCEEDED")
        print()
        print("DEPLOYMENT BLOCKED")

    # Verbose mode for developers
    if verbose:
        print()
        print("DETAILS")
        print("────────────────────────")
        print()
        print("Cache:")
        print(f"  Hits:       {summary.cache_hits}")
        print(f"  API calls:  {summary.api_calls}")
        print()
        print("Azure:")
        primary_res = summary.resource_costs[0] if summary.resource_costs else None
        if primary_res:
            print(f"  Region:     {primary_res.region}")
            print(f"  SKU:        {primary_res.new_sku or primary_res.old_sku or 'N/A'}")
            print("  Price type: Consumption")
        if summary.skipped_resources:
            print()
            print("Skipped:")
            print(f"  {len(summary.skipped_resources)} non-billable resources")
        if summary.warnings:
            print()
            print("Warnings:")
            for w in summary.warnings:
                print(f"  ⚠ {w}")


def render_json_report(summary: FinancialSummary, verdict: PolicyVerdict) -> str:
    """Generate structured JSON representation of financial analysis."""
    payload = {
        "currency": summary.currency,
        "financial_summary": {
            "prior_monthly_total": summary.prior_monthly_total,
            "projected_monthly_total": summary.projected_monthly_total,
            "net_monthly_impact": summary.net_monthly_impact,
            "annualized_impact": summary.net_monthly_impact * 12.0,
        },
        "policy_verdict": {
            "budget_threshold": verdict.budget_threshold,
            "status": "PASSED" if verdict.passed else "FAILED",
            "passed": verdict.passed,
            "exit_code": verdict.exit_code,
            "message": verdict.message,
        },
        "cache_statistics": {
            "cache_hits": summary.cache_hits,
            "cache_misses": summary.cache_misses,
            "api_calls": summary.api_calls,
        },
        "resources": [
            {
                "address": r.address,
                "type": r.resource_type,
                "action": r.action,
                "region": r.region,
                "old_sku": r.old_sku,
                "new_sku": r.new_sku,
                "old_monthly_cost": r.old_monthly_cost,
                "new_monthly_cost": r.new_monthly_cost,
                "delta": r.delta,
                "warning": r.warning,
            }
            for r in summary.resource_costs
        ],
        "skipped_resources": summary.skipped_resources,
        "warnings": summary.warnings,
    }
    return json.dumps(payload, indent=2)


def render_markdown_report(summary: FinancialSummary, verdict: PolicyVerdict) -> str:
    """Generate clean GitHub-flavored Markdown report suitable for PR comments / CI."""
    symbol = CURRENCY_SYMBOLS.get(summary.currency, "₹")
    lines = [
        "## CostGuard — Azure Infrastructure Cost Impact Report\n",
        f"**Status:** {'🟢 WITHIN BUDGET' if verdict.passed else '🔴 BUDGET EXCEEDED'}\n",
        "### Financial Summary\n",
        f"- **Current Monthly Cost:** {symbol}{summary.prior_monthly_total:,.2f}/month",
        f"- **Projected Monthly Cost:** {symbol}{summary.projected_monthly_total:,.2f}/month",
        f"- **Monthly Impact:** {'+' if summary.net_monthly_impact > 0 else ''}{symbol}{summary.net_monthly_impact:,.2f}/month",
        f"- **Annualized Impact:** {'+' if summary.net_monthly_impact > 0 else ''}{symbol}{(summary.net_monthly_impact * 12):,.2f}/year",
        f"- **Budget:** {f'{symbol}{verdict.budget_threshold:,.2f}/month' if verdict.budget_threshold is not None else 'Unconstrained'}",
    ]

    if summary.resource_costs:
        lines.append("\n### Cost Impact Breakdown\n")
        lines.append(f"| Resource | Action | Current | Projected | Impact |")
        lines.append("|---|:---:|---:|---:|---:|")
        for r in summary.resource_costs:
            name = format_resource_name(r.address, r.resource_type)
            action = "UPDATE" if r.action in ("UPDATE", "REPLACE") else r.action
            curr_str = format_money(r.old_monthly_cost, symbol=symbol)
            proj_str = format_money(r.new_monthly_cost, symbol=symbol)
            impact_str = format_money(r.delta, symbol=symbol, show_sign=True)
            lines.append(f"| `{name}` | {action} | {curr_str} | {proj_str} | {impact_str} |")
        lines.append("")

    if not verdict.passed:
        lines.append("> ⚠️ **Deployment Blocked:** Projected monthly increase exceeds budget limit.\n")

    return "\n".join(lines)
