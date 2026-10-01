"""Unit tests for the SQLite pricing cache and VM pricing filter."""

import tempfile
from pathlib import Path

from costguard.pricing.azure import filter_vm_pricing_items
from costguard.pricing.cache import PricingCache


def test_cache_miss_and_set():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        cache = PricingCache(db_path=tmp.name)

        # Initial lookup must miss
        rate = cache.get("Standard_B2s", "eastus", "INR")
        assert rate is None
        hits, misses = cache.get_stats()
        assert hits == 0
        assert misses == 1

        # Store rate
        cache.set("Standard_B2s", "eastus", "INR", 3.99)

        # Second lookup must hit
        rate2 = cache.get("Standard_B2s", "eastus", "INR")
        assert rate2 == 3.99
        hits, misses = cache.get_stats()
        assert hits == 1
        assert misses == 1


def test_cache_currency_isolation():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        cache = PricingCache(db_path=tmp.name)

        cache.set("Standard_B2s", "eastus", "INR", 4.00)
        cache.set("Standard_B2s", "eastus", "USD", 0.05)

        assert cache.get("Standard_B2s", "eastus", "INR") == 4.00
        assert cache.get("Standard_B2s", "eastus", "USD") == 0.05
        assert cache.get("Standard_B2s", "eastus", "EUR") is None


def test_cache_clear():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        cache = PricingCache(db_path=tmp.name)
        cache.set("SKU_A", "eastus", "INR", 10.0)
        cache.set("SKU_B", "eastus", "INR", 20.0)

        assert cache.get("SKU_A", "eastus", "INR") == 10.0

        deleted = cache.clear()
        assert deleted == 2

        assert cache.get("SKU_A", "eastus", "INR") is None
        assert cache.get("SKU_B", "eastus", "INR") is None


def test_vm_pricing_filter_rejects_spot_and_low_priority():
    items = [
        {
            "priceType": "Consumption",
            "meterName": "B2s Spot",
            "skuName": "B2s Spot",
            "retailPrice": 1.25,
            "unitOfMeasure": "1 Hour",
        },
        {
            "priceType": "Consumption",
            "meterName": "B2s Low Priority",
            "skuName": "B2s Low Priority",
            "retailPrice": 1.50,
            "unitOfMeasure": "1 Hour",
        },
        {
            "priceType": "Reservation",
            "meterName": "B2s 1 Year",
            "retailPrice": 2.00,
            "unitOfMeasure": "1 Hour",
        },
        {
            "priceType": "Consumption",
            "meterName": "B2s",
            "skuName": "B2s",
            "retailPrice": 3.99,
            "unitOfMeasure": "1 Hour",
            "isPrimaryMeterRegion": True,
        },
    ]

    selected = filter_vm_pricing_items(items)
    assert selected is not None
    assert selected["retailPrice"] == 3.99
    assert selected["meterName"] == "B2s"


def test_vm_pricing_filter_empty_list():
    assert filter_vm_pricing_items([]) is None


def test_vm_pricing_filter_all_rejected():
    items = [
        {
            "priceType": "Consumption",
            "meterName": "B2s Spot",
            "skuName": "B2s Spot",
            "retailPrice": 1.25,
        },
        {
            "priceType": "Reservation",
            "meterName": "B2s",
            "retailPrice": 2.00,
        },
    ]
    assert filter_vm_pricing_items(items) is None
