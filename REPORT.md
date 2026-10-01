# CostGuard Project Report

## 1. What We Built

CostGuard is a standalone, production-quality Command Line Interface (CLI) application and automated FinOps circuit breaker written in Python. It analyzes Terraform execution plans (`terraform show -json tfplan`) before infrastructure changes are applied to Microsoft Azure, calculates the exact monthly financial impact using live data from the official Azure Retail Prices API, caches rates locally using SQLite, and enforces automated budget policies.

The core motivation is simple: developers and platform engineers often modify Terraform code without immediate awareness of the cost consequences until the monthly cloud invoice arrives. CostGuard shifts cost observability to the earliest possible phase of the engineering lifecycle (pull requests and CI/CD pipelines), preventing accidental overspending before a single cloud resource is provisioned.

---

## 2. Architecture

CostGuard follows a modular, single-responsibility architecture to prevent congestion and ensure beginner-friendly code clarity.

```text
                     Terraform JSON Plan
                              │
                              ▼
                   costguard/parser/terraform.py
            (Action mapping, SKU, region, & billables)
                              │
                              ▼
                   costguard/pricing/engine.py
                   /                        \
      (Cache Hit) /                          \ (Cache Miss)
                 ▼                            ▼
      costguard/pricing/cache.py     costguard/pricing/azure.py
        (SQLite write-through)       (Azure Retail API & OData)
                 \                            /
                  \                          /
                   ▼                        ▼
                costguard/accounting/calculator.py
            (730 hours/month & action matrix deltas)
                              │
                              ▼
                  costguard/policy/guardrail.py
            (Threshold evaluation & circuit breaker)
                              │
                              ▼
                   costguard/ui/terminal.py
            (Rich tables, panels, JSON, & Markdown)
```

The system is organized into focused sub-packages:
- **`costguard.config`**: Central configuration, ARM region normalization dictionary, currency settings, and standard exit codes.
- **`costguard.models`**: Strongly typed domain models (`ResourceChange`, `ResourceCost`, `FinancialSummary`, `PolicyVerdict`).
- **`costguard.parser`**: Ingests Terraform plan JSON, resolves actions, extracts VM and disk configurations, and detects metadata-only updates.
- **`costguard.pricing`**: Coordinates SQLite caching and live Azure Retail Prices API queries with strict consumption filters.
- **`costguard.accounting`**: Converts hourly rates into monthly costs using the FinOps standard of 730 hours/month and computes individual and aggregate deltas.
- **`costguard.policy`**: Evaluates budget thresholds, generates circuit-breaker alerts, and returns exact exit codes (0, 1, or 2).
- **`costguard.ui`**: Renders terminal UI via `rich`, structured JSON for CI automation, and Markdown for pull request comments.

---

## 3. Detection and Extraction Logic

The parser parses the `resource_changes` array from a Terraform execution plan.

### Action Resolution
Terraform describes changes using string action arrays:
- `["create"]` $\rightarrow$ `CREATE`
- `["delete"]` $\rightarrow$ `DELETE`
- `["update"]` $\rightarrow$ `UPDATE`
- `["delete", "create"]` or `["create", "delete"]` $\rightarrow$ `REPLACE`
- `["no-op"]` or `["read"]` $\rightarrow$ `NO-OP`

### Resource Extraction Strategy
An extensible dictionary of extractors isolates resource-specific property mapping:
- **Virtual Machines** (`azurerm_linux_virtual_machine`, `azurerm_virtual_machine`, `azurerm_windows_virtual_machine`): Extracts `size` or `vm_size`, `location`, and OS type.
- **Managed Disks** (`azurerm_managed_disk`): Extracts `storage_account_type` and `disk_size_gb`.
- **Non-Billable Resources**: Explicitly identifies non-billables (`azurerm_resource_group`, `azurerm_virtual_network`, `azurerm_subnet`, `azurerm_network_security_group`, etc.), marks them as `is_billable = False`, and skips them safely with zero cost.
- **Metadata-Only Changes**: If an `update` action occurs but `before.size == after.size` and `before.location == after.location` (e.g., updating only tags, description, or computer name), CostGuard sets `is_metadata_only = True`, guaranteeing a ₹0.00 cost delta.

### ARM Region Normalization
Azure regions may appear as friendly names (`East US`, `Central India`, `West Europe`) or ARM slugs (`eastus`, `centralindia`, `westeurope`). CostGuard normalizes all regional strings through a mapping table and regex slugifier, ensuring accurate API queries and cache keys.

---

## 4. Azure Retail Pricing Integration

CostGuard communicates with the official Microsoft Azure Retail Prices API:

```text
https://prices.azure.com/api/retail/prices
```

- **Query Construction**: Builds OData query filters:
  ```text
  $filter=serviceName eq 'Virtual Machines' and armRegionName eq '{region}' and armSkuName eq '{sku}' and priceType eq 'Consumption'
  ```
- **Live Currency Requests**: Appends `currencyCode=INR` (or USD, EUR, GBP) to ensure rates are localized by Microsoft's engine without fabricating currency exchange rates.
- **Network Resilience**: Encapsulates network operations with timeouts and exception handling (`urllib.error.URLError`, HTTP status codes). If the network is unreachable, CostGuard relies on the local cache; if no cached price exists, it warns gracefully without crashing.

---

## 5. SQLite Cache

CostGuard implements a mandatory write-through cache in `pricing_cache.db`:

```sql
CREATE TABLE IF NOT EXISTS pricing_cache (
    sku TEXT NOT NULL,
    region TEXT NOT NULL,
    currency TEXT NOT NULL,
    hourly_rate REAL NOT NULL,
    cached_at INTEGER NOT NULL,
    PRIMARY KEY (sku, region, currency)
);
```

- **Composite Key**: `(sku, region, currency)` ensures prices are isolated by region and currency.
- **Hit vs. Miss Tracking**: Tracks `cache_hits`, `cache_misses`, and `api_calls`.
- **Cache Invalidation / Clear**: The `--clear-cache` flag executes a fast `DELETE FROM pricing_cache;` and reports the number of deleted records.

---

## 6. Pricing Filter Strategy

Azure's pricing API frequently returns multiple entries for a single SKU. Without intelligent filtering, an application could select a Spot rate, a Low Priority rate, or a multi-year reserved discount, distorting on-demand cost forecasts.

CostGuard isolates this logic into `filter_vm_pricing_items(items)`:
1. Filters for `priceType == "Consumption"`.
2. Inspects `meterName`, `skuName`, and `productName` to reject any items containing `"spot"` or `"low priority"`.
3. Validates positive `retailPrice` and standard `1 Hour` unit of measure.
4. Prefers primary meter regions (`isPrimaryMeterRegion == True`).

---

## 7. Accounting Method

- **Hours Per Month**: Standard FinOps assumption of $730.0\text{ hours/month}$.
- **Monthly Cost**: $\text{monthly\_cost} = \text{hourly\_rate} \times 730$.
- **Action Matrix**:
  - `CREATE`: $\text{Old} = 0$, $\text{New} = \text{Monthly}$, $\Delta = +\text{New}$
  - `DELETE`: $\text{Old} = \text{Monthly}$, $\text{New} = 0$, $\Delta = -\text{Old}$ (strictly negative delta representing financial savings)
  - `UPDATE`: $\Delta = \text{New Monthly} - \text{Old Monthly}$ (positive for upgrades, negative for downgrades)
  - `REPLACE`: $\Delta = \text{New Monthly} - \text{Old Monthly}$
  - `NO-OP` / `METADATA`: $\Delta = 0.00$
- **Total Invariant**: $\sum \text{deltas} \equiv \text{Projected Total} - \text{Prior Total}$.

---

## 8. Budget Guardrail

The `--max-increase` option defines the maximum permissible net monthly increase:
- **Savings & Neutral Changes**: If $\Delta_{\text{net}} \le 0$, the plan represents cost reductions and always passes.
- **Within Threshold**: If $\Delta_{\text{net}} \le \text{Threshold}$, the verdict is `PASSED` (Exit Code `0`).
- **Threshold Breached**: If $\Delta_{\text{net}} > \text{Threshold}$, the verdict is `FAILED` (Exit Code `1`). A prominent `[CIRCUIT BREAKER]` message displays the exact financial overage.

---

## 9. Test Results

The test suite contains 34 comprehensive tests run via `pytest -v`:
- `tests/test_parser.py`: 8 tests (action types, region normalization, create/delete/update/replace parsing, metadata-only changes, non-billables, JSON error handling).
- `tests/test_cache.py`: 6 tests (cache miss/set, currency isolation, cache clear, spot/low-priority filter, empty list, all rejected).
- `tests/test_accounting.py`: 6 tests (730 hours, create positive, delete negative, upgrade, downgrade, metadata-only zero cost).
- `tests/test_guardrail.py`: 6 tests (unconstrained, below threshold, equal threshold, above threshold, savings pass, zero impact pass).
- `tests/test_integration.py`: 8 tests (end-to-end runs with plan-create, plan-delete, plan-noise, budget breach, JSON output, Markdown output, invalid input exit 2, cache clear).

**Result**: 34 passed in 0.59s (100% pass rate).

---

## 10. Results Matrix

The table below reflects the actual execution outputs obtained by running CostGuard against the live Azure Retail Prices API with INR currency and a budget threshold of ₹5,000.00:

| Test Plan | Action Description | Billable Resources | Prior Monthly | Projected Monthly | Actual Impact ($\Delta$) | Policy Verdict | Exit Code |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Plan 1** (`plan-create.json`) | Create Standard_B2s VM in East US | 1 | ₹0.00 | ₹2,915.04 | **+₹2,915.04/mo** | PASSED (within ₹5,000 budget) | **0** |
| **Plan 1 (Strict)** (`plan-create.json`) | Create Standard_B2s with ₹1,000 ceiling | 1 | ₹0.00 | ₹2,915.04 | **+₹2,915.04/mo** | FAILED (Breached by ₹1,915.04) | **1** |
| **Plan 2** (`plan-delete.json`) | Delete Standard_B1s VM in East US | 1 | ₹981.05 | ₹0.00 | **-₹981.05/mo** | PASSED (Savings) | **0** |
| **Plan 3** (`plan-update.json`) | Upgrade Standard_B1s $\rightarrow$ B2s | 1 | ₹981.05 | ₹2,915.04 | **+₹1,933.99/mo** | PASSED (within ₹5,000 budget) | **0** |
| **Plan 4** (`plan-noise.json`) | 16 non-billable networking & RG resources | 0 | ₹0.00 | ₹0.00 | **₹0.00/mo** | PASSED (Zero cost impact) | **0** |
| **Invalid Input** (`bad.json`) | Malformed JSON input | N/A | N/A | N/A | N/A | ERROR (Invalid JSON) | **2** |

---

## 11. Limitations

1. **Static vs. Dynamic Metering**: CostGuard forecasts infrastructure provisioning costs (VM compute instances, storage disks). Dynamic runtime usage metrics (egress network bandwidth, storage transaction counts) cannot be known before code execution.
2. **Enterprise Agreement (EA) Negotiated Rates**: The Azure Retail Prices API serves standard public pay-as-you-go consumption rates. Organizations with proprietary discounted EA contracts will observe public retail list prices rather than negotiated rates.

---

## 12. Future Improvements

1. **Expanded Resource Providers**: Add extractors for Azure App Services (`azurerm_app_service_plan`), Azure SQL Database (`azurerm_mssql_database`), and Azure Kubernetes Service (AKS).
2. **GitLab CI / GitHub Actions Custom Action**: Package CostGuard as a pre-built GitHub Action that automatically posts Markdown cost summaries directly as pull request comments.
3. **Multi-Cloud Generalization**: Extend the parser and pricing abstraction to support AWS (AWS Price List API) and Google Cloud (Cloud Billing API).

---

## 13. How to Run

```bash
# 1. View CLI help
costguard --help

# 2. Run analysis on create plan
costguard --plan test-plans/plan-create.json --max-increase 5000

# 3. Test budget circuit breaker (breach)
costguard --plan test-plans/plan-create.json --max-increase 1000

# 4. Run via pipeline
cat test-plans/plan-update.json | costguard --max-increase 5000

# 5. Clear cache
costguard --clear-cache

# 6. Run test suite
pytest -v
```

---

## 14. Conclusion

CostGuard demonstrates that automated FinOps guardrails can be lightweight, fast, deterministic, and reliable. By combining Terraform JSON plan parsing, the official Azure Retail Prices API, and a local SQLite write-through cache, CostGuard provides engineering teams with instant financial feedback, blocking costly configuration mistakes before they deploy to the cloud.
