"""Typed data structures and domain models for CostGuard."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ResourceChange:
    """Represents a single parsed Terraform resource change."""

    address: str
    resource_type: str
    actions: list[str]
    action_type: str  # "create" | "delete" | "update" | "replace" | "no-op"
    region: str
    old_sku: Optional[str] = None
    new_sku: Optional[str] = None
    is_billable: bool = True
    is_metadata_only: bool = False
    skip_reason: Optional[str] = None
    extra_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceCost:
    """Calculated cost impact for an individual billable resource."""

    address: str
    resource_type: str
    action: str
    region: str
    old_sku: Optional[str]
    new_sku: Optional[str]
    old_hourly_rate: float
    new_hourly_rate: float
    old_monthly_cost: float
    new_monthly_cost: float
    delta: float
    currency: str
    warning: Optional[str] = None

    @property
    def display_sku(self) -> str:
        """Formatted representation of the SKU change."""
        if self.action in ("update", "replace"):
            if self.old_sku == self.new_sku:
                return self.new_sku or "N/A"
            return f"{self.old_sku or 'None'} → {self.new_sku or 'None'}"
        elif self.action == "create":
            return self.new_sku or "N/A"
        elif self.action == "delete":
            return self.old_sku or "N/A"
        return self.new_sku or self.old_sku or "N/A"


@dataclass
class FinancialSummary:
    """Aggregated financial impact across all resources in the plan."""

    prior_monthly_total: float
    projected_monthly_total: float
    net_monthly_impact: float
    currency: str
    cache_hits: int
    cache_misses: int
    api_calls: int
    resource_costs: list[ResourceCost] = field(default_factory=list)
    skipped_resources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PolicyVerdict:
    """Outcome of evaluating budget guardrails."""

    budget_threshold: Optional[float]
    net_monthly_impact: float
    currency: str
    passed: bool
    status_label: str  # "PASSED" | "FAILED"
    message: str
    exit_code: int
