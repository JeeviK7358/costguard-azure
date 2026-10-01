"""CostGuard: Azure Infrastructure Cost Impact Predictor.

A standalone CLI tool and FinOps guardrail that analyzes Terraform JSON plans,
calculates monthly cost impact via the Azure Retail Prices API, caches rates
in SQLite, and enforces budget thresholds.
"""

__version__ = "1.0.0"
