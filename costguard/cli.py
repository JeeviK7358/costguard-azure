"""Clean and minimal Command Line Interface (CLI) entry point for CostGuard."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from costguard.accounting.calculator import calculate_plan_financials
from costguard.config import (
    DEFAULT_CURRENCY,
    DEFAULT_DB_PATH,
    EXIT_CODE_ERROR,
    SUPPORTED_CURRENCIES,
)
from costguard.parser.terraform import parse_terraform_plan
from costguard.policy.guardrail import evaluate_budget_guardrail
from costguard.pricing.cache import PricingCache
from costguard.pricing.engine import PricingEngine
from costguard.ui.terminal import (
    print_cost_report,
    render_json_report,
    render_markdown_report,
)


class CostGuardArgumentParser(argparse.ArgumentParser):
    """Custom parser providing clean, focused help output."""

    def format_help(self) -> str:
        return (
            "CostGuard — Terraform Azure Cost Guardrail\n\n"
            "Usage:\n"
            "  costguard --plan <file> --max-increase <INR>\n\n"
            "Examples:\n"
            "  costguard --plan plan.json --max-increase 5000\n"
            "  cat plan.json | costguard --max-increase 5000\n\n"
            "Options:\n"
            "  --plan FILE           Terraform JSON plan\n"
            "  --max-increase INR    Maximum allowed monthly increase\n"
            "  --verbose             Show detailed information\n"
            "  --clear-cache         Clear cached prices\n"
            "  --help                Show help\n"
        )


def create_argument_parser() -> argparse.ArgumentParser:
    """Configure CLI command line options and arguments."""
    parser = CostGuardArgumentParser(
        prog="costguard",
        add_help=False,  # We handle --help cleanly
    )

    parser.add_argument(
        "--help",
        "-h",
        action="help",
        help="Show help",
    )

    parser.add_argument(
        "--plan",
        "-p",
        dest="plan_path",
        type=str,
        default=None,
        help="Terraform JSON plan",
    )

    parser.add_argument(
        "--max-increase",
        "-m",
        dest="max_increase",
        type=float,
        default=None,
        help="Maximum allowed monthly increase",
    )

    parser.add_argument(
        "--currency",
        "-c",
        dest="currency",
        type=str,
        default=DEFAULT_CURRENCY,
        choices=SUPPORTED_CURRENCIES,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--clear-cache",
        dest="clear_cache",
        action="store_true",
        help="Clear cached prices",
    )

    parser.add_argument(
        "--cache-db",
        dest="cache_db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--markdown",
        dest="output_markdown",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--verbose",
        "-v",
        dest="verbose",
        action="store_true",
        help="Show detailed information",
    )

    return parser


def read_plan_input(plan_path: Optional[str]) -> str:
    """Read plan JSON string from file path or standard input."""
    if plan_path:
        p = Path(plan_path)
        if not p.is_file():
            print(f"Error: Plan file '{plan_path}' does not exist.", file=sys.stderr)
            sys.exit(EXIT_CODE_ERROR)
        try:
            return p.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Error: Could not read plan file '{plan_path}': {exc}", file=sys.stderr)
            sys.exit(EXIT_CODE_ERROR)

    # Check if input is piped into stdin
    if not sys.stdin.isatty():
        try:
            content = sys.stdin.read()
            if not content.strip():
                print("Error: Standard input was empty. Expected Terraform JSON plan.", file=sys.stderr)
                sys.exit(EXIT_CODE_ERROR)
            return content
        except Exception as exc:
            print(f"Error: Could not read from stdin: {exc}", file=sys.stderr)
            sys.exit(EXIT_CODE_ERROR)

    print("Error: No Terraform plan provided. Pass --plan <file> or pipe JSON via stdin.", file=sys.stderr)
    sys.exit(EXIT_CODE_ERROR)


def run_cli(args: Optional[list[str]] = None) -> int:
    """Execute CostGuard CLI with specified arguments."""
    parser = create_argument_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit as exc:
        return exc.code

    cache = PricingCache(db_path=parsed_args.cache_db)

    # Handle cache clear request
    if parsed_args.clear_cache:
        deleted_count = cache.clear()
        print(f"Pricing cache cleared ({deleted_count} records removed).")
        return 0

    # Read plan JSON
    plan_raw = read_plan_input(parsed_args.plan_path)

    # Parse Terraform JSON plan
    try:
        changes = parse_terraform_plan(plan_raw)
    except ValueError:
        print("Error: Invalid Terraform JSON plan.", file=sys.stderr)
        return EXIT_CODE_ERROR

    # Run pricing engine & calculations
    pricing_engine = PricingEngine(cache=cache, verbose=parsed_args.verbose)
    summary = calculate_plan_financials(
        changes=changes,
        pricing_engine=pricing_engine,
        currency=parsed_args.currency.upper(),
    )

    # Evaluate budget guardrail
    verdict = evaluate_budget_guardrail(
        net_monthly_impact=summary.net_monthly_impact,
        max_increase=parsed_args.max_increase,
        currency=parsed_args.currency.upper(),
    )

    # Render results
    if parsed_args.output_json:
        print(render_json_report(summary, verdict))
    elif parsed_args.output_markdown:
        print(render_markdown_report(summary, verdict))
    else:
        print_cost_report(summary, verdict, verbose=parsed_args.verbose)

    return verdict.exit_code


def main() -> None:
    """Standard console script entry point."""
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
