"""Parser for Terraform JSON execution plans."""

import json
from typing import Any, Dict, List, Optional, Tuple

from costguard.config import (
    BILLABLE_RESOURCE_TYPES,
    NON_BILLABLE_RESOURCE_TYPES,
    normalize_region,
)
from costguard.models import ResourceChange


def resolve_action_type(actions: List[str]) -> str:
    """Map Terraform action lists to canonical action types.

    Examples:
        ["create"] -> "create"
        ["delete"] -> "delete"
        ["update"] -> "update"
        ["delete", "create"] -> "replace"
        ["create", "delete"] -> "replace"
        ["no-op"] -> "no-op"
        ["read"] -> "no-op"
    """
    actions_set = set(actions)
    if actions == ["create"]:
        return "create"
    if actions == ["delete"]:
        return "delete"
    if actions == ["update"]:
        return "update"
    if "create" in actions_set and "delete" in actions_set:
        return "replace"
    if "no-op" in actions_set or "read" in actions_set:
        return "no-op"
    if not actions:
        return "no-op"
    # Fallback to first action
    return actions[0]


def extract_vm_attributes(
    before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str], str, bool, Dict[str, Any]]:
    """Extract VM SKU, region, and metadata flags from before/after states.

    Returns:
        (old_sku, new_sku, region, is_metadata_only, extra_attributes)
    """
    before_dict = before or {}
    after_dict = after or {}

    old_sku = before_dict.get("size") or before_dict.get("vm_size")
    new_sku = after_dict.get("size") or after_dict.get("vm_size")

    raw_location = (
        after_dict.get("location")
        or before_dict.get("location")
        or "eastus"
    )
    region = normalize_region(raw_location)

    # Check for metadata-only updates
    # If both before and after exist with identical size and location,
    # then this change (e.g. tags, os_profile) has zero cost impact.
    is_metadata_only = False
    if before and after:
        same_sku = (old_sku is not None and old_sku == new_sku)
        loc_before = normalize_region(before_dict.get("location"))
        loc_after = normalize_region(after_dict.get("location"))
        same_region = (loc_before == loc_after)
        if same_sku and same_region:
            is_metadata_only = True

    extra = {
        "os_type": after_dict.get("os_profile", {}).get("os_type")
        or before_dict.get("os_profile", {}).get("os_type")
    }

    return old_sku, new_sku, region, is_metadata_only, extra


def extract_disk_attributes(
    before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str], str, bool, Dict[str, Any]]:
    """Extract Managed Disk SKU, size, region, and metadata flags.

    Returns:
        (old_sku, new_sku, region, is_metadata_only, extra_attributes)
    """
    before_dict = before or {}
    after_dict = after or {}

    old_tier = before_dict.get("storage_account_type")
    new_tier = after_dict.get("storage_account_type")

    old_size = before_dict.get("disk_size_gb")
    new_size = after_dict.get("disk_size_gb")

    raw_location = (
        after_dict.get("location")
        or before_dict.get("location")
        or "eastus"
    )
    region = normalize_region(raw_location)

    # Build representative SKU, e.g. "StandardSSD_LRS_128GB"
    old_sku = f"{old_tier}_{old_size}GB" if old_tier and old_size else old_tier
    new_sku = f"{new_tier}_{new_size}GB" if new_tier and new_size else new_tier

    is_metadata_only = False
    if before and after:
        if old_tier == new_tier and old_size == new_size:
            is_metadata_only = True

    extra = {
        "storage_account_type": new_tier or old_tier,
        "disk_size_gb": new_size or old_size,
    }

    return old_sku, new_sku, region, is_metadata_only, extra


# Resource extractor registry to easily support new Azure resource types
RESOURCE_EXTRACTORS = {
    "azurerm_linux_virtual_machine": extract_vm_attributes,
    "azurerm_virtual_machine": extract_vm_attributes,
    "azurerm_windows_virtual_machine": extract_vm_attributes,
    "azurerm_managed_disk": extract_disk_attributes,
}


def parse_terraform_plan(plan_data: Dict[str, Any] | str) -> List[ResourceChange]:
    """Parse a Terraform JSON plan into a list of typed ResourceChange objects.

    Args:
        plan_data: Parsed dictionary or JSON string of Terraform execution plan.

    Returns:
        List of ResourceChange instances.

    Raises:
        ValueError: If the input JSON is malformed or invalid structure.
    """
    if isinstance(plan_data, str):
        try:
            plan_dict = json.loads(plan_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Terraform JSON: {exc}") from exc
    elif isinstance(plan_data, dict):
        plan_dict = plan_data
    else:
        raise ValueError("Invalid plan data type. Expected JSON string or dictionary.")

    if not isinstance(plan_dict, dict):
        raise ValueError("Root Terraform plan must be a JSON object.")

    resource_changes_raw = plan_dict.get("resource_changes")
    if resource_changes_raw is None:
        # Some plans might be empty or just format_version, handle gracefully
        return []

    if not isinstance(resource_changes_raw, list):
        raise ValueError("'resource_changes' in Terraform plan must be a list.")

    parsed_changes: List[ResourceChange] = []

    for item in resource_changes_raw:
        if not isinstance(item, dict):
            continue

        address = item.get("address", "unknown_resource")
        res_type = item.get("type", "unknown_type")
        change_obj = item.get("change", {})
        actions = change_obj.get("actions", ["no-op"])
        before = change_obj.get("before")
        after = change_obj.get("after")

        action_type = resolve_action_type(actions)

        # Check if billable
        if res_type in BILLABLE_RESOURCE_TYPES:
            extractor = RESOURCE_EXTRACTORS.get(res_type)
            if extractor:
                old_sku, new_sku, region, is_metadata_only, extra = extractor(before, after)
            else:
                old_sku, new_sku, region, is_metadata_only, extra = None, None, "eastus", False, {}

            parsed_changes.append(
                ResourceChange(
                    address=address,
                    resource_type=res_type,
                    actions=actions,
                    action_type=action_type,
                    region=region,
                    old_sku=old_sku,
                    new_sku=new_sku,
                    is_billable=True,
                    is_metadata_only=is_metadata_only,
                    extra_attributes=extra,
                )
            )
        else:
            # Non-billable resource (e.g., networking, resource groups)
            raw_location = None
            if isinstance(after, dict):
                raw_location = after.get("location")
            if not raw_location and isinstance(before, dict):
                raw_location = before.get("location")
            region = normalize_region(raw_location)

            parsed_changes.append(
                ResourceChange(
                    address=address,
                    resource_type=res_type,
                    actions=actions,
                    action_type=action_type,
                    region=region,
                    is_billable=False,
                    skip_reason=f"Non-billable resource type: {res_type}",
                )
            )

    return parsed_changes
