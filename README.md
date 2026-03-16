# Huckle

**Decision intelligence for industrial operations.**

Huckle connects to the operational systems a company already runs, watches all of them simultaneously, and tells senior leaders what is about to happen — with evidence, financial scenarios, and a recommended action.

**[→ Live Demo — Meridian Glass & Aluminum](https://huckle-public.vercel.app)**

---

## What It Looks Like

A nightly intelligence scan finds a convergence of signals across three connected systems:

```
Signal:         Plant utilization dropping  →  72% (z-score: -1.8)
Signal:         Order backlog accelerating  →  +38% (z-score: +2.1)
Signal:         Labor shift capacity        →  constrained

Prediction:     Capacity risk — demand outpacing available labor capacity
Horizon:        30–60 days
Confidence:     0.82

Recommended:    Open weekend shift at Atlanta facility
Financial:      +$340K revenue protected · $28K labor cost · Net: +$312K
```

This is what the daily briefing looks like. Not a dashboard. Not a report. A typed prediction with a recommended action and the financial case for taking it.

**[→ See it live](https://huckle-public.vercel.app)**

---

## The Problem It Solves

Industrial manufacturers operate with a fundamental information lag. CRM shows what salespeople did today. ERP shows what happened last month. Maintenance tracks work orders after the fact. Nothing shows what will happen in 90 days.

Demand softens in the pipeline 60 days before it shows in backlog. Commodity prices compress margin 30–60 days before the P&L reflects it. PM compliance declining at a facility predicts unplanned downtime 4–6 weeks out.

Good operators feel this coming. But they're reading three to five disconnected systems, running the numbers in their head, and making judgment calls on incomplete, lagging data.

Huckle connects those systems, reads them simultaneously, and delivers the signal before the event.

---

## Quick Start — Run the Demo Locally

```bash
git clone https://github.com/The-Resonance-Institute/huckle-public.git
cd huckle-public
pip install -r requirements.txt
python demo.py
```

The demo runs against Meridian Glass & Aluminum synthetic data — three facilities, 18 active signals, live predictions, and Intelligence Chat.

---

## Architecture

Six-layer pipeline. Each layer reads only from the layer immediately below it. This constraint is enforced in code and in tests.

```
L1  Connected data sources    CRM · ERP · CMMS · feeds · file uploads
         ↓
L2  Canonical data layer       Normalized, deduplicated, immutable records
         ↓
L3  Signal engine              18 signal types · z-scores · directional scoring
         ↓
L4  Prediction engine          Typed predictions · confidence scores · narratives
         ↓
L5  Simulation engine          Conservative · Balanced · Aggressive scenarios
         ↓
L6  Decision ledger            Append-only · T+30/60/90 outcome tracking
```

---

## What It Connects To

Pre-built connectors ship for the most common industrial systems. Custom connectors follow a two-method interface and can be built for any system with a REST API or structured export.

**CRM** — Zoho · Salesforce · HubSpot · Dynamics CRM · any REST API

**ERP** — Dynamics AX/D365 · SAP · Oracle · Epicor · Infor · any OData or REST

**CMMS** — Fiix · MaintainX · eMaint · IBM Maximo · UpKeep · Limble · any REST API

**Quality / Production** — QMS · MES · SPC · any production data source

**HR / Labor** — ADP · Workday · Paylocity · any payroll API

**Data warehouses** — Snowflake · BigQuery · Redshift · Azure Synapse · any SQL

**File-based** — Excel · CSV · SharePoint · any structured file format

**External feeds** — FRED · ABI · LME commodity prices · Dodge Construction · Census · any structured API

---

## Signal Library

18 pre-built signal types. Every signal computed against a 24-month rolling baseline using population z-scores — calibrated to the customer's own operational history, not industry averages.

| Category | Signals |
|----------|---------|
| CRM | Pipeline velocity · Pipeline decay · Win rate · Stage stall · Contact cadence |
| ERP | Backlog burn · Capacity utilization · Labor efficiency · Inventory coverage · Budget drift |
| Operations — Labor | Labor productivity · Yield rate |
| Operations — Materials | Material cost variance · Scrap rate |
| Operations — Maintenance | Unplanned downtime rate · PM compliance |
| External | Composite macro index · Commodity pressure |

---

## Predictions

Three typed prediction models ship pre-built:

- **Demand inflection** — CRM leading indicators show meaningful shift in demand direction
- **Capacity risk** — ERP and operations signals show mismatch between capacity and projected demand
- **Margin pressure** — Commodity, cost, and material signals indicate incoming margin compression

Each prediction includes confidence score, time horizon, plain-language narrative, and recommended action. Adverse predictions with High or Medium confidence automatically trigger the simulation engine.

---

## Scenarios

For every adverse prediction, three financial scenarios generated from the customer's actual cost structure:

| Scenario | Approach |
|----------|---------|
| **Conservative** | Maximum cost reduction. Protect margin through variable cost cuts. |
| **Balanced** | Moderate reduction. Preserve core capacity and recovery optionality. |
| **Aggressive** | Hold capacity. Invest through the cycle. Accept short-term compression. |

Each scenario outputs revenue impact at 30 and 90 days, cost reduction achievable, headcount change, net outcome, payback period, and plain-language narrative.

---

## Intelligence Chat

Natural language Q&A grounded in the customer's actual connected data.

> *"Why is Charlotte's yield declining?"*

Gets an answer citing the actual signal values, z-scores, and trends from that facility's data. Not general knowledge. Their numbers.

---

## Decision Ledger

Append-only record of every leader decision — enforced at three levels: PostgreSQL trigger, application model, and integration tests. Captures prediction and simulation at decision time, signal snapshot, action taken, and outcome classified at T+30/60/90.

After 18 months of recorded decisions and validated outcomes, the ledger is the institutional memory of the business. It compounds with every entry.

---

## CASA Governance

Every agent action in Huckle passes through [CASA Runtime](https://github.com/The-Resonance-Institute/casa-runtime) before execution — a deterministic pre-execution governance gate that evaluates every action as a 9-field Canonical Action Vector and returns ACCEPT, GOVERN, or REFUSE before anything executes.

```
Huckle detects signal
         ↓
Prediction engine proposes action
         ↓
CASA evaluates admissibility
         ↓
Execute or halt
```

Every verdict is recorded to an append-only audit table. CASA is covered by USPTO Provisional Patent #63/987,813.

---

## Daily Briefing

Every morning, senior leaders receive an HTML email containing:

- Signal summary — direction and z-score for all active signals
- Active predictions — what the system expects in the next 30–90 days
- Scenario analysis — financial outcomes for each response path
- Intelligence observations — cross-system findings from the nightly agent
- Decisions required — adverse predictions awaiting a leadership response
- Recent outcomes — how prior predictions performed at T+30/60/90

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

## Vertical Focus

Pre-built signals and connectors are calibrated for industrial manufacturing. The chassis is vertical-agnostic — the canonical data model, signal framework, governance layer, and briefing engine work for any industry with structured operational data.

---

## Contact

Built by [The Resonance Institute, LLC](https://theresonanceinstitute.com).

For enterprise pilot inquiries, partnership discussions, or acquisition conversations:
**[contact@resonanceinstitutellc.com](mailto:contact@resonanceinstitutellc.com)**

If you experiment with Huckle in an operational context, open an issue and share what you find.

---

*Huckle platform code is proprietary. The connector framework in this repository is open for community contributions. Signal engine, prediction engine, simulation engine, decision ledger, and intelligence agent are maintained in a private repository.*

*CASA architecture covered by USPTO Provisional Patent #63/987,813. © 2026 The Resonance Institute, LLC.*
