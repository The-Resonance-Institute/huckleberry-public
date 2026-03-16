# Huckleberry

**Configurable decision intelligence for industrial operations.**

Huckleberry is a decision intelligence chassis. It connects to the operational data systems a company already runs — CRM, ERP, CMMS, quality systems, data warehouses, payroll platforms, file uploads, industry feeds, macro economic indicators — and turns that data into forward-looking intelligence that senior leaders can act on.

It answers one question that no existing system answers:

> *"What is about to happen to my business — and what should I do about it now?"*

Every deployment is configured to the customer's systems, data sources, industry vertical, and operational priorities. The chassis ships with pre-built connectors, a signal library, and a governance layer. What gets connected, what gets monitored, and what gets surfaced in the daily briefing is configured per deployment.

**[→ Live Demo — Meridian Glass & Aluminum](https://huckleberry-public.vercel.app)**

---

## The problem

Industrial manufacturers operate with a fundamental information lag. Their CRM tells them what salespeople are doing today. Their ERP tells them what happened last month. Their maintenance system tracks work orders after the fact. None of it tells them what will happen in 90 days.

Demand softens in the pipeline 60 days before it shows in backlog. Commodity prices compress margin 30-60 days before the P&L reflects it. PM compliance declining at a facility predicts unplanned downtime 4-6 weeks out. A yield drop from 94% to 89% is a margin event — but it's invisible until the month closes.

Good operators feel this coming. But they're reading three to five disconnected systems, running the numbers in their head, and making judgment calls with incomplete, lagging information.

Huckleberry connects those systems, reads them simultaneously, and tells the leader what is about to happen — with evidence, confidence ratings, financial scenarios, and a recommended action.

---

## Architecture

Huckleberry is built as a strict six-layer pipeline. Each layer reads only from the layer immediately below it.

```
L1  Connected data sources    Any system with structured data
         ↓
L2  Canonical data layer       Normalized, deduplicated, immutable records
         ↓
L3  Signal engine              Configurable signal library with z-scores and directions
         ↓
L4  Prediction engine          Typed predictions with confidence scoring and narratives
         ↓
L5  Simulation engine          Conservative · Balanced · Aggressive financial scenarios
         ↓
L6  Decision ledger            Append-only record with T+30/60/90 accuracy tracking
```

No layer skips another. This constraint is enforced in code and in tests.

---

## Configurability

Huckleberry ships as a chassis. Each deployment is configured to the customer's environment.

**What ships pre-built:**
- Connector framework with interfaces for CRM, ERP, CMMS, external feeds, and file uploads
- Pre-built connectors for Zoho CRM, Salesforce, Microsoft Dynamics AX, Fiix, MaintainX, FRED, ABI, and LME
- Signal library with 18 pre-built signal types across commercial, operational, maintenance, and macro domains
- Prediction engine with three typed prediction models
- Simulation engine with Conservative / Balanced / Aggressive scenario framework
- CASA governance layer (pre-execution AI action governance)
- Daily briefing engine with HTML email delivery
- Intelligence Chat (natural language Q&A grounded in connected data)

**What gets configured per deployment:**
- Which systems to connect (any system below)
- Which signals to activate and weight
- Which industry-specific metrics matter for this vertical
- Macro and industry feeds relevant to this market
- Facility structure and organizational hierarchy
- Briefing recipients, timing, and content priorities
- Alert thresholds and escalation paths

---

## What it can connect to

Huckleberry's connector framework is designed to attach to any structured data source. Pre-built connectors exist for the most common industrial systems. Custom connectors follow the same two-method interface contract and can be built for any system with a REST API or structured data export.

**CRM systems**
Zoho CRM · Salesforce · HubSpot · Microsoft Dynamics CRM · Any CRM with REST API

**ERP systems**
Microsoft Dynamics AX / D365 · SAP · Oracle ERP · Epicor · Infor · Any ERP with OData or REST

**CMMS / Maintenance systems**
Fiix · MaintainX · eMaint · Infor EAM · IBM Maximo · UpKeep · Limble · MP2 · Any CMMS with REST API

**Quality and production systems**
Quality management systems (QMS) · MES (Manufacturing Execution Systems) · SPC systems · Any production data source

**HR and labor systems**
ADP · Workday · Paylocity · Any payroll or labor management system with API access

**Data warehouses and analytics platforms**
Snowflake · BigQuery · Redshift · Azure Synapse · Any SQL-queryable data warehouse

**File-based sources**
Excel (.xlsx, .xls) · CSV · Shared folders · SharePoint · Any structured file format

**External feeds (configurable per deployment)**
FRED (Federal Reserve Economic Data) · ABI (Architecture Billings Index) · LME commodity prices · Dodge Construction Network · Census Bureau · Industry association data · Commodity price feeds · Any data source with a structured API

**Industry news and events (configurable)**
Industry publications · Tariff and trade policy feeds · Competitor monitoring · Regulatory change feeds · Any news source relevant to the customer's market

---

## Signal library

18 pre-built signal types ship with the platform. Additional signal types are added as new data sources are connected. Every signal is computed against a 24-month rolling baseline using population z-scores — calibrated to each customer's own operational history, not industry averages.

| Category | Pre-built signals |
|----------|---------|
| **CRM** | Pipeline velocity · Pipeline decay · Win rate · Stage stall · Contact cadence |
| **ERP** | Backlog burn · Capacity utilization · Labor efficiency · Inventory coverage · Budget drift |
| **Operations — Labor** | Labor productivity · Yield rate |
| **Operations — Materials** | Material cost variance · Scrap rate |
| **Operations — Maintenance** | Unplanned downtime rate · PM compliance |
| **External** | Composite macro index · Commodity pressure |

Each deployment activates the signals relevant to its connected data sources and adds custom signals for metrics specific to that vertical or operation.

---

## Predictions

Three typed prediction models ship pre-built. Additional prediction types are configured per deployment based on what matters in that industry and operating environment.

- **Demand inflection** — CRM leading indicators show meaningful shift in demand direction
- **Capacity risk** — ERP and operations signals show mismatch between current capacity and projected demand
- **Margin pressure** — Commodity, cost, and material signals indicate incoming margin compression

Each prediction includes a confidence score, time horizon, Claude-generated narrative, and recommended action. Adverse predictions with High or Medium confidence automatically trigger the simulation engine.

---

## Scenarios

For every adverse prediction, three financial scenarios are generated from the customer's actual cost structure:

| Scenario | Approach |
|----------|---------|
| **Conservative** | Maximum cost reduction. Protect margin through variable cost cuts and headcount reduction. |
| **Balanced** | Moderate cost reduction. Preserve core capacity and optionality for demand recovery. |
| **Aggressive** | Hold capacity. Invest through the cycle. Accept short-term margin compression. |

Each scenario outputs revenue impact at 30 and 90 days, cost reduction achievable, headcount change, net outcome at 90 days, payback period, and a plain-language narrative.

---

## Exploratory intelligence agent

Beyond the structured signal pipeline, a nightly exploratory intelligence agent runs with full read-only access to all connected data sources. It does not look for pre-defined patterns. It runs four bounded analytic procedures across the entire connected data surface:

1. **Anomaly scan** — values deviating significantly from rolling baseline not caught by standard signals
2. **Cross-system correlation** — patterns spanning two or more connected systems simultaneously
3. **Trend acceleration** — signals moving faster than their current z-score indicates
4. **File and upload reconciliation** — manually uploaded data vs system records discrepancies

Every finding is recorded as a typed `IntelligenceObservation` with structured evidence fields — not just prose. The LLM narrates from evidence. It does not determine what is significant — the analytic procedures do.

If nothing clears the evidence threshold, zero observations are written. The agent does not invent findings.

---

## Intelligence Chat

Every deployment includes an Intelligence Chat interface — a natural language Q&A panel grounded in the customer's actual connected data. Leaders ask questions in plain English and get specific answers that cite real signal values, z-scores, and trends from their own systems.

"Why is Charlotte's yield declining?" gets an answer that cites the actual numbers, the contributing signals, and what the prediction engine expects next. Not general knowledge. Their data.

---

## CASA governance

Every agent action in Huckleberry passes through the [CASA Runtime](https://github.com/The-Resonance-Institute/casa-runtime) before execution. CASA (Constitutional AI Safety Architecture) is a deterministic pre-execution governance gate — not a safety layer, but a structural access control system.

Every action is described as a 9-field Canonical Action Vector and evaluated against a constitutional graph. The gate returns ACCEPT, GOVERN, or REFUSE before any action executes. Every verdict is recorded to an append-only audit table.

CASA is covered by USPTO Provisional Patent #63/987,813.

---

## Decision ledger

The Decision Ledger is the most strategically valuable component of the platform. It is an append-only record of every leader decision — enforced at three levels: PostgreSQL trigger, application model, and integration tests.

Every entry captures the prediction and simulation that drove the decision, a signal snapshot at decision time, the action taken, and the outcome classified at T+30/60/90. Over time, the ledger builds an institutional memory of signal state → decision → outcome that no other system captures.

---

## Daily briefing

Every morning, senior leaders receive an HTML email briefing containing:

- Signal summary — direction and z-score for all active signals
- Active predictions — what the system expects in the next 30-90 days
- Scenario analysis — financial outcomes for each response path
- Intelligence observations — cross-system findings from the nightly agent
- Decisions required — adverse predictions awaiting a leadership response
- Recent outcomes — how prior predictions performed at T+30/60/90

Briefing content, recipients, timing, and section priorities are configured per deployment.

---

## Infrastructure

Deployed on AWS. Fully defined in Terraform.

| Component | Service |
|-----------|---------|
| Compute | ECS Fargate |
| Database | RDS PostgreSQL 15 |
| Orchestration | MWAA (Managed Airflow) |
| Cache | ElastiCache Redis |
| Queuing | SQS (with DLQs) |
| Auth | Cognito (JWT) |
| Secrets | Secrets Manager |
| CDN | CloudFront |

**Scheduled workloads:**
- Connector sync every 30 minutes
- Signal computation every 4 hours
- External feed ingestion daily at 06:00 UTC
- Intelligence scan nightly at 03:00 UTC
- Prediction validation nightly at 02:00 UTC
- Briefing delivery at customer-configured time

---

## Build

```
146 Python source files
1,582 tests passing · 0 failures
18 Terraform files
15 database tables
18 pre-built signal types (extensible)
6 pre-built connector types (extensible)
6 MWAA DAGs
```

---

## Demo

The live demo runs against synthetic data for a fictional glass and aluminum fabricator — Meridian Glass & Aluminum — with three facilities (Atlanta, Charlotte, Memphis). It shows the full platform surface: all 18 signals, active predictions with scenarios, intelligence observations, facility drill-down, budget tracking, and the Intelligence Chat.

**[→ Launch demo](https://huckleberry-public.vercel.app)**

---

## Vertical focus

The pre-built signal library and prediction models are calibrated for industrial manufacturing — glass fabricators, building materials companies, HVAC distributors, aluminum processors, steel service centers. The connector set covers the systems most common in this vertical.

The chassis is vertical-agnostic. The canonical data model, signal framework, governance layer, and briefing engine work for any industry with structured operational data. Deployments in other verticals configure the signal library and connectors appropriate to that environment.

---

## Contact

Built by [The Resonance Institute, LLC](https://theresonanceinstitute.com).

For enterprise pilot inquiries, partnership discussions, or acquisition conversations:
**[contact@resonanceinstitutellc.com](mailto:contact@resonanceinstitutellc.com)**

---

*Huckleberry platform code is proprietary. The connector framework in this repository is open for community contributions. The signal engine, prediction engine, simulation engine, decision ledger, and intelligence agent are maintained in a private repository.*

*CASA architecture covered by USPTO Provisional Patent #63/987,813. © 2026 The Resonance Institute, LLC.*
