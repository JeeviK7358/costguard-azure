"""Coordinating Pricing Engine with SQLite Write-Through Cache."""

from typing import Any, Dict, Optional, Tuple

from costguard.pricing.azure import fetch_azure_price
from costguard.pricing.cache import PricingCache


class PricingEngine:
    """Orchestrates pricing lookups between the local SQLite cache and the Azure Retail API."""

    def __init__(self, cache: Optional[PricingCache] = None, verbose: bool = False):
        self.cache = cache or PricingCache()
        self.api_calls = 0
        self.verbose = verbose

    def resolve_hourly_price(
        self,
        sku: Optional[str],
        region: str,
        currency: str = "INR",
        resource_type: str = "azurerm_linux_virtual_machine",
        extra_attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[float]:
        """Resolve hourly rate for a SKU using write-through cache logic.

        1. Check SQLite cache.
        2. If HIT -> Return cached rate immediately.
        3. If MISS -> Call official Azure Retail Prices API.
        4. If API returns rate -> Save to SQLite cache, return rate.
        5. If API fails / missing -> Return None (graceful skipping).

        Args:
            sku: Resource SKU name.
            region: Normalized ARM region.
            currency: Currency code.
            resource_type: Terraform resource type.
            extra_attributes: Optional extra metadata.

        Returns:
            Hourly rate as float, or None if unresolvable.
        """
        if not sku or not region:
            return None

        # Step 1: Check SQLite cache first
        cached_rate = self.cache.get(sku, region, currency)
        if cached_rate is not None:
            return cached_rate

        # Step 2: Cache miss -> Query Azure Retail Prices API
        self.api_calls += 1
        live_rate = fetch_azure_price(
            sku=sku,
            region=region,
            currency=currency,
            resource_type=resource_type,
            extra_attributes=extra_attributes,
            verbose=self.verbose,
        )

        if live_rate is not None and live_rate >= 0:
            # Step 3: Write-through to SQLite cache
            self.cache.set(sku, region, currency, live_rate)
            return live_rate

        return None

    def get_stats(self) -> Tuple[int, int, int]:
        """Return (cache_hits, cache_misses, api_calls)."""
        hits, misses = self.cache.get_stats()
        return hits, misses, self.api_calls
