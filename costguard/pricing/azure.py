"""Integration with the official Azure Retail Prices API."""

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from costguard.config import AZURE_RETAIL_API_URL

logger = logging.getLogger(__name__)


def filter_vm_pricing_items(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Filter Azure Retail API items for standard, on-demand VM consumption pricing.

    Rejection criteria:
    - Must NOT be Spot or Low Priority pricing.
    - Must be Consumption / on-demand (priceType == 'Consumption').
    - Must have a positive retail price.
    - Matches standard compute unit of measure (e.g., '1 Hour').

    Args:
        items: List of item dictionaries returned by the Azure Retail API.

    Returns:
        The most appropriate pricing item dictionary, or None if no valid match.
    """
    if not items:
        return None

    valid_candidates: List[Dict[str, Any]] = []

    for item in items:
        price_type = item.get("priceType") or item.get("type")
        if price_type != "Consumption":
            continue

        meter_name = str(item.get("meterName", "")).lower()
        sku_name = str(item.get("skuName", "")).lower()
        product_name = str(item.get("productName", "")).lower()

        # Reject Spot and Low Priority instances
        if "spot" in meter_name or "spot" in sku_name or "spot" in product_name:
            continue
        if "low priority" in meter_name or "low priority" in sku_name or "low priority" in product_name:
            continue

        retail_price = item.get("retailPrice")
        if retail_price is None or float(retail_price) < 0:
            continue

        valid_candidates.append(item)

    if not valid_candidates:
        return None

    # Prefer primary meter region items if multiple exist
    for cand in valid_candidates:
        if cand.get("isPrimaryMeterRegion") is True:
            return cand

    # Prefer 1 Hour unit of measure
    for cand in valid_candidates:
        unit = str(cand.get("unitOfMeasure", "")).lower()
        if "hour" in unit or "1 hour" in unit:
            return cand

    # Default to first valid candidate
    return valid_candidates[0]


def filter_disk_pricing_items(items: List[Dict[str, Any]], disk_size_gb: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Filter Azure Retail API items for Managed Disks consumption pricing."""
    if not items:
        return None

    valid_candidates: List[Dict[str, Any]] = []
    for item in items:
        price_type = item.get("priceType") or item.get("type")
        if price_type != "Consumption":
            continue

        meter_name = str(item.get("meterName", "")).lower()
        sku_name = str(item.get("skuName", "")).lower()

        if "spot" in meter_name or "low priority" in meter_name:
            continue

        retail_price = item.get("retailPrice")
        if retail_price is None or float(retail_price) < 0:
            continue

        valid_candidates.append(item)

    if not valid_candidates:
        return None

    for cand in valid_candidates:
        if cand.get("isPrimaryMeterRegion") is True:
            return cand

    return valid_candidates[0]


def fetch_azure_price(
    sku: str,
    region: str,
    currency: str = "INR",
    resource_type: str = "azurerm_linux_virtual_machine",
    extra_attributes: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 10.0,
    verbose: bool = False,
) -> Optional[float]:
    """Fetch on-demand retail pricing for an Azure resource SKU from the official API.

    Args:
        sku: Azure SKU (e.g., 'Standard_B2s').
        region: ARM region name (e.g., 'eastus').
        currency: 3-letter currency code (e.g., 'INR').
        resource_type: Terraform resource type.
        extra_attributes: Additional attributes.
        timeout_sec: Network timeout in seconds.
        verbose: If True, prints diagnostic lookup messages.

    Returns:
        Hourly rate as float, or None if not found or on network failure.
    """
    if not sku or not region:
        return None

    is_vm = "virtual_machine" in resource_type
    is_disk = "managed_disk" in resource_type

    # Construct OData filter query
    if is_vm:
        odata_filter = (
            f"serviceName eq 'Virtual Machines' "
            f"and armRegionName eq '{region}' "
            f"and armSkuName eq '{sku}' "
            f"and priceType eq 'Consumption'"
        )
    elif is_disk:
        clean_sku = sku.split("_")[0]
        odata_filter = (
            f"serviceName eq 'Storage' "
            f"and armRegionName eq '{region}' "
            f"and contains(skuName, '{clean_sku}') "
            f"and priceType eq 'Consumption'"
        )
    else:
        odata_filter = (
            f"armRegionName eq '{region}' "
            f"and armSkuName eq '{sku}' "
            f"and priceType eq 'Consumption'"
        )

    params = {
        "$filter": odata_filter,
        "currencyCode": currency.upper(),
    }

    url = f"{AZURE_RETAIL_API_URL}?{urllib.parse.urlencode(params)}"

    if verbose:
        print(f"[Verbose] Fetching price from Azure Retail API for {sku} ({region})...")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CostGuard/1.0 (Azure Cost Impact Predictor)",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            if response.status != 200:
                print(f"⚠ Could not reach Azure Retail Prices API (HTTP {response.status}).")
                return None

            raw_body = response.read().decode("utf-8")
            data = json.loads(raw_body)
            items = data.get("Items", [])

            if not items:
                print(f"⚠ Price unavailable for {sku}.")
                return None

            if is_vm:
                selected_item = filter_vm_pricing_items(items)
            elif is_disk:
                selected_item = filter_disk_pricing_items(items)
            else:
                selected_item = items[0]

            if not selected_item:
                print(f"⚠ Price unavailable for {sku}.")
                return None

            unit_price = float(selected_item.get("retailPrice", 0.0))
            unit_of_measure = str(selected_item.get("unitOfMeasure", "")).lower()

            if "month" in unit_of_measure and unit_price > 0:
                return unit_price / 730.0

            return unit_price

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as err:
        if verbose:
            print(f"⚠ Could not get pricing for {sku} ({err}).\n  This resource was skipped.")
        else:
            print(f"⚠ Could not get pricing for {sku}.\n  This resource was skipped.")
        return None
    except json.JSONDecodeError:
        print(f"⚠ Could not get pricing for {sku}.\n  This resource was skipped.")
        return None
