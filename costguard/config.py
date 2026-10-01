"""Configuration constants and region normalization for CostGuard."""

import re

# Currency settings
DEFAULT_CURRENCY = "INR"
SUPPORTED_CURRENCIES = ["INR", "USD", "EUR", "GBP"]
CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

# Runtime and billing assumptions
HOURS_PER_MONTH = 730.0

# Database
DEFAULT_DB_PATH = "pricing_cache.db"

# Official Azure Retail Prices API endpoint
AZURE_RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# CLI Exit Codes
EXIT_CODE_SUCCESS = 0         # Analysis succeeded and budget within threshold
EXIT_CODE_BUDGET_EXCEEDED = 1 # Budget increase threshold was exceeded
EXIT_CODE_ERROR = 2           # Invalid input / invalid JSON / bad arguments

# Billable Terraform Azure resource types supported
BILLABLE_RESOURCE_TYPES = {
    "azurerm_linux_virtual_machine",
    "azurerm_virtual_machine",
    "azurerm_windows_virtual_machine",
    "azurerm_managed_disk",
}

# Explicit non-billable Azure resource types commonly found in plans
NON_BILLABLE_RESOURCE_TYPES = {
    "azurerm_resource_group",
    "azurerm_virtual_network",
    "azurerm_subnet",
    "azurerm_network_security_group",
    "azurerm_network_security_rule",
    "azurerm_network_interface",
    "azurerm_route_table",
    "azurerm_route",
    "azurerm_public_ip_prefix",
    "azurerm_private_dns_zone",
    "azurerm_private_dns_zone_virtual_network_link",
}

# Azure Region Name Mapping for robust normalization
AZURE_REGION_MAP = {
    "east us": "eastus",
    "east us 2": "eastus2",
    "west us": "westus",
    "west us 2": "westus2",
    "west us 3": "westus3",
    "central us": "centralus",
    "north central us": "northcentralus",
    "south central us": "southcentralus",
    "west europe": "westeurope",
    "north europe": "northeurope",
    "central india": "centralindia",
    "south india": "southindia",
    "west india": "westindia",
    "southeast asia": "southeastasia",
    "east asia": "eastasia",
    "uk south": "uksouth",
    "uk west": "ukwest",
    "france central": "francecentral",
    "france south": "francesouth",
    "germany west central": "germanywestcentral",
    "germany north": "germanynorth",
    "australia east": "australiaeast",
    "australia southeast": "australiasoutheast",
    "australia central": "australiacentral",
    "canada central": "canadacentral",
    "canada east": "canadaeast",
    "japan east": "japaneast",
    "japan west": "japanwest",
    "korea central": "koreacentral",
    "korea south": "koreasouth",
    "brazil south": "brazilsouth",
    "switzerland north": "switzerlandnorth",
    "switzerland west": "switzerlandwest",
    "sweden central": "swedencentral",
    "norway east": "norwayeast",
    "south africa north": "southafricanorth",
    "uae north": "uaenorth",
}


def normalize_region(location: str | None) -> str:
    """Normalize Azure location names into valid ARM region identifiers.

    Examples:
        'East US' -> 'eastus'
        'EAST US' -> 'eastus'
        'Central India' -> 'centralindia'
        'eastus' -> 'eastus'
    """
    if not location:
        return "eastus"

    clean = location.strip().lower()

    # Check exact match in dictionary
    if clean in AZURE_REGION_MAP:
        return AZURE_REGION_MAP[clean]

    # Normalize by removing extra whitespaces, dashes, and underscores
    slug = re.sub(r"[\s\-_]+", "", clean)
    if slug in AZURE_REGION_MAP.values():
        return slug

    # If already a lowercase slug or custom region, return stripped slug
    return slug
