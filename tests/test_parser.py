"""Unit tests for the Terraform Plan Parser module."""

import pytest
from costguard.config import normalize_region
from costguard.parser.terraform import parse_terraform_plan, resolve_action_type


def test_resolve_action_types():
    assert resolve_action_type(["create"]) == "create"
    assert resolve_action_type(["delete"]) == "delete"
    assert resolve_action_type(["update"]) == "update"
    assert resolve_action_type(["delete", "create"]) == "replace"
    assert resolve_action_type(["create", "delete"]) == "replace"
    assert resolve_action_type(["no-op"]) == "no-op"
    assert resolve_action_type(["read"]) == "no-op"
    assert resolve_action_type([]) == "no-op"


def test_region_normalization():
    assert normalize_region("East US") == "eastus"
    assert normalize_region("east us") == "eastus"
    assert normalize_region("EAST US") == "eastus"
    assert normalize_region("Central India") == "centralindia"
    assert normalize_region("West Europe") == "westeurope"
    assert normalize_region("uksouth") == "uksouth"
    assert normalize_region("UK South") == "uksouth"
    assert normalize_region(None) == "eastus"


def test_parse_create_action():
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_linux_virtual_machine.web",
                "type": "azurerm_linux_virtual_machine",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "size": "Standard_B2s",
                        "location": "East US",
                    },
                },
            }
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 1
    c = changes[0]
    assert c.address == "azurerm_linux_virtual_machine.web"
    assert c.action_type == "create"
    assert c.is_billable is True
    assert c.region == "eastus"
    assert c.old_sku is None
    assert c.new_sku == "Standard_B2s"
    assert c.is_metadata_only is False


def test_parse_delete_action():
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_virtual_machine.old_box",
                "type": "azurerm_virtual_machine",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "vm_size": "Standard_D2s_v3",
                        "location": "Central US",
                    },
                    "after": None,
                },
            }
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 1
    c = changes[0]
    assert c.action_type == "delete"
    assert c.region == "centralus"
    assert c.old_sku == "Standard_D2s_v3"
    assert c.new_sku is None


def test_parse_update_action():
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_linux_virtual_machine.db",
                "type": "azurerm_linux_virtual_machine",
                "change": {
                    "actions": ["update"],
                    "before": {
                        "size": "Standard_B1s",
                        "location": "West Europe",
                    },
                    "after": {
                        "size": "Standard_B2s",
                        "location": "West Europe",
                    },
                },
            }
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 1
    c = changes[0]
    assert c.action_type == "update"
    assert c.region == "westeurope"
    assert c.old_sku == "Standard_B1s"
    assert c.new_sku == "Standard_B2s"
    assert c.is_metadata_only is False


def test_parse_replacement_action():
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_linux_virtual_machine.runner",
                "type": "azurerm_linux_virtual_machine",
                "change": {
                    "actions": ["delete", "create"],
                    "before": {
                        "size": "Standard_B1ms",
                        "location": "East US",
                    },
                    "after": {
                        "size": "Standard_B2ms",
                        "location": "East US",
                    },
                },
            }
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 1
    assert changes[0].action_type == "replace"
    assert changes[0].old_sku == "Standard_B1ms"
    assert changes[0].new_sku == "Standard_B2ms"


def test_metadata_only_changes():
    # Only tags or computer_name changed, size and location stay identical
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_linux_virtual_machine.tagged_vm",
                "type": "azurerm_linux_virtual_machine",
                "change": {
                    "actions": ["update"],
                    "before": {
                        "size": "Standard_B2s",
                        "location": "East US",
                        "tags": {"Environment": "Dev"},
                    },
                    "after": {
                        "size": "Standard_B2s",
                        "location": "East US",
                        "tags": {"Environment": "Production"},
                    },
                },
            }
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 1
    assert changes[0].is_metadata_only is True


def test_non_billable_resources():
    plan = {
        "resource_changes": [
            {
                "address": "azurerm_resource_group.rg",
                "type": "azurerm_resource_group",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"location": "East US"},
                },
            },
            {
                "address": "azurerm_virtual_network.vnet",
                "type": "azurerm_virtual_network",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"location": "East US"},
                },
            },
        ]
    }
    changes = parse_terraform_plan(plan)
    assert len(changes) == 2
    assert all(c.is_billable is False for c in changes)


def test_invalid_json_handling():
    with pytest.raises(ValueError, match="Invalid Terraform JSON"):
        parse_terraform_plan("not-a-valid-json")

    with pytest.raises(ValueError, match="Root Terraform plan must be a JSON object"):
        parse_terraform_plan("[1, 2, 3]")
