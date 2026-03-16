# Contributing to Huckleberry

The Huckleberry connector framework is open for community contributions. If your business runs a system that Huckleberry doesn't connect to yet, you can build the connector and submit a PR. Every connector you add becomes available to every Huckleberry deployment.

---

## What you can contribute

**New connectors** — the highest-value contribution. If you work with a system not already covered (SAP, Oracle, Epicor, Infor, UpKeep, Limble, Workday, custom ERP, industry-specific platforms), building a connector makes Huckleberry available to every business running that system.

**Connector improvements** — additional fields, better normalization, pagination fixes, rate limit handling, new API versions.

**External feed connectors** — macro economic data sources, industry association feeds, commodity price sources, government data APIs.

---

## How connectors work

Every Huckleberry connector implements a simple two-method contract defined in `connectors/base.py`. The platform calls these methods on a schedule. Your connector fetches data from the source system, normalizes it to the canonical schema, and returns typed record objects. That's it.

The platform handles everything else: storage, signal computation, prediction generation, briefing delivery. You just need to fetch and normalize.

**CRM connectors** implement:
- `fetch_commercial_events()` → list of `CommercialEventRecord`

**ERP connectors** implement:
- `fetch_operational_metrics()` → list of `OperationalMetricRecord`

**CMMS connectors** implement:
- `fetch_work_orders()` → `WorkOrderFetchResult`
- `fetch_assets()` → `AssetFetchResult`

**External feed connectors** implement:
- `fetch_signals()` → list of `ExternalSignalRecord`

See `connectors/base.py` for the full interface definitions and field contracts.

---

## Step-by-step: adding a new connector

**Step 1 — Pick the right category folder**

```
connectors/crm/        CRM and sales systems
connectors/erp/        ERP, MES, and production systems
connectors/cmms/       Maintenance management systems
connectors/external/   Macro, industry, and market data feeds
```

**Step 2 — Copy the example connector**

```bash
cp examples/custom_erp_example.py connectors/erp/your_system.py
```

**Step 3 — Implement the interface**

Open your new file and implement the required methods. The example connector walks through every field with inline comments. The key rules:

- Credentials are loaded from environment variables or Secrets Manager — never hardcoded
- All fetch methods are read-only — never write back to the source system
- Return `None` from normalization methods for records that can't be parsed cleanly
- Use `_safe_decimal()` and `_safe_datetime()` helpers from the base class for type conversion

**Step 4 — Register your connector**

Open `connectors/registry.py` and add your connector to the appropriate registry dict:

```python
ERP_CONNECTORS = {
    "dynamics_ax": DynamicsAXConnector,
    "your_system":  YourSystemConnector,   # add this line
}
```

**Step 5 — Add a health check**

Implement `_validate_credentials()` in your connector. This is called during onboarding to verify the connection before any data is fetched.

**Step 6 — Submit a PR**

Open a pull request with:
- Your connector file
- Updated registry.py
- A brief description of the source system and which fields you mapped

---

## Field mapping

The `connectors/field_mapper.py` module handles normalization from source-specific field names to the canonical schema. If your source system uses non-standard field names, add a mapping entry rather than hardcoding transformations in the connector itself. This keeps connectors clean and makes field mapping auditable.

---

## Code standards

- Python 3.11+
- Type hints on all method signatures
- Docstrings on all public methods
- No hardcoded credentials
- No writes to source systems
- `_safe_decimal()` and `_safe_datetime()` for all type conversions

---

## Questions

Open an issue or email contact@resonanceinstitutellc.com.
