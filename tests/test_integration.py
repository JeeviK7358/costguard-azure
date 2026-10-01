"""Integration tests for CostGuard CLI workflow."""

from pathlib import Path
from costguard.cli import run_cli
from costguard.config import (
    EXIT_CODE_BUDGET_EXCEEDED,
    EXIT_CODE_ERROR,
    EXIT_CODE_SUCCESS,
)


def test_cli_plan_create_passed(tmp_path):
    cache_file = tmp_path / "test_cache.db"
    exit_code = run_cli([
        "--plan", "test-plans/plan-create.json",
        "--max-increase", "5000",
        "--cache-db", str(cache_file),
    ])
    assert exit_code == EXIT_CODE_SUCCESS


def test_cli_plan_create_budget_breached(tmp_path):
    cache_file = tmp_path / "test_cache.db"
    exit_code = run_cli([
        "--plan", "test-plans/plan-create.json",
        "--max-increase", "500",  # 500 INR is lower than ~2900 INR cost
        "--cache-db", str(cache_file),
    ])
    assert exit_code == EXIT_CODE_BUDGET_EXCEEDED


def test_cli_plan_delete_passed(tmp_path):
    cache_file = tmp_path / "test_cache.db"
    exit_code = run_cli([
        "--plan", "test-plans/plan-delete.json",
        "--max-increase", "1000",
        "--cache-db", str(cache_file),
    ])
    assert exit_code == EXIT_CODE_SUCCESS


def test_cli_plan_noise_zero_impact(tmp_path):
    cache_file = tmp_path / "test_cache.db"
    exit_code = run_cli([
        "--plan", "test-plans/plan-noise.json",
        "--max-increase", "1000",
        "--cache-db", str(cache_file),
    ])
    assert exit_code == EXIT_CODE_SUCCESS


def test_cli_json_and_markdown_output(tmp_path, capsys):
    cache_file = tmp_path / "test_cache.db"
    # Test JSON flag
    exit_code_json = run_cli([
        "--plan", "test-plans/plan-noise.json",
        "--json",
        "--cache-db", str(cache_file),
    ])
    assert exit_code_json == EXIT_CODE_SUCCESS
    out_json, _ = capsys.readouterr()
    import json
    data = json.loads(out_json)
    assert data["financial_summary"]["net_monthly_impact"] == 0.0
    assert data["policy_verdict"]["status"] == "PASSED"

    # Test Markdown flag
    exit_code_md = run_cli([
        "--plan", "test-plans/plan-noise.json",
        "--markdown",
        "--cache-db", str(cache_file),
    ])
    assert exit_code_md == EXIT_CODE_SUCCESS
    out_md, _ = capsys.readouterr()
    assert "CostGuard — Azure Infrastructure Cost Impact Report" in out_md


def test_cli_invalid_json_exit_2(tmp_path):
    bad_plan = tmp_path / "bad.json"
    bad_plan.write_text("invalid json content {{{")

    exit_code = run_cli([
        "--plan", str(bad_plan),
        "--cache-db", str(tmp_path / "cache.db"),
    ])
    assert exit_code == EXIT_CODE_ERROR


def test_cli_clear_cache(tmp_path, capsys):
    cache_file = tmp_path / "cache_to_clear.db"
    exit_code = run_cli(["--clear-cache", "--cache-db", str(cache_file)])
    assert exit_code == EXIT_CODE_SUCCESS
    captured = capsys.readouterr()
    assert "Pricing cache cleared" in captured.out
