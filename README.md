# Huckleberry

**Decision intelligence for industrial manufacturing.**

Huckleberry connects to a company's CRM, ERP, and maintenance systems as a read-only data consumer. It computes leading indicators from that data, generates typed predictions with confidence ratings, models the financial impact of response scenarios, and delivers a daily executive briefing to senior leaders.

It answers one question that no existing system answers:

> *"What is about to happen to my business — and what should I do about it now?"*

**[→ Live Demo — Meridian Glass & Aluminum](https://demo.huckleberry.ai)**

---

## The problem

Industrial manufacturers operate with a fundamental information lag. Their CRM tells them what salespeople are doing today. Their ERP tells them what happened last month. Neither tells them what will happen in 90 days.

Demand softens in the pipeline 60 days before it shows in backlog. Commodity prices compress margin 30-60 days before the P&L reflects it. PM compliance declining at a facility predicts unplanned downtime 4-6 weeks out. A yield drop from 94% to 89% on a production line is a margin event — but it's invisible until the month closes.

Good operators make reactive decisions with good judgment. Huckleberry makes it possible to make proactive decisions with systematic intelligence.

---

## Architecture

Huckleberry is built as a strict six-layer pipeline. Each layer reads only from the layer immediately below it.

```
L1  Source systems      CRM · ERP · CMMS · External feeds
         ↓
L2  Canonical data      CommercialEvent · OperationalMetric · ExternalSignal
         ↓
L3  Signal engine       18 ComputedSignal types with z-scores and directions
         ↓
L4  Prediction engine   Typed predictions with confidence scoring and narratives
         ↓
L5  Simulation engine   Conservative · Balanced · Aggressive financial scenarios
         ↓
L6  Decision ledger     Append-only decision record with T+30/60/90 accuracy tracking
```

No layer skips another. This constraint is enforced in code and in tests.

---

## Signals

18 signal types computed against a 24-month rolling baseline using population z-scores.

| Category | Signals |
|----------|---------|
| **CRM** | Pipeline velocity · Pipeline decay · Win rate · Stage stall · Contact cadence |
| **ERP** | Backlog burn · Capacity utilization · Labor efficiency · Inventory coverage · Budget drift |
| **Operations — Labor** | Labor productivity · Yield rate |
| **Operations — Materials** | Material cost variance · Scrap rate |
| **Operations — Maintenance** | Unplanned downtime rate · PM compliance |
| **External** | Composite macro index · Commodity pressure |

Every signal produces a z-score, a direction label (improving / stable / softening / deteriorating), and a reliability score. Signals with degraded data quality automatically reduce prediction confidence.

---

## Predictions

Three typed prediction models, each driven by a different signal cluster:

- **Demand inflection** — CRM leading indicators show meaningful shift in demand direction
- **Capacity risk** — ERP signals show mismatch between current capacity and projected demand
- **Margin pressure** — Commodity and cost signals indicate incoming margin compression

Each prediction includes a confidence score (High / Medium / Low / Insufficient Data), a time horizon (30, 60, or 90 days), a Claude-generated narrative, and a recommended action. Adverse predictions with High or Medium confidence automatically trigger simulation engine.

---

## Scenarios

For every adverse prediction, three financial scenarios are generated from the customer's ERP cost structure:

| Scenario | Approach |
|----------|---------|
| **Conservative** | Maximum cost reduction. Protect margin through variable cost cuts and headcount reduction. |
| **Balanced** | Moderate cost reduction. Preserve core capacity and optionality for demand recovery. |
| **Aggressive** | Hold capacity. Invest through the cycle. Accept short-term margin compression. |

Each scenario outputs revenue impact at 30 and 90 days, cost reduction achievable, headcount change, net outcome at 90 days, payback period, and a plain-language narrative.

---

## Connector framework

Huckleberry connects as a **read-only consumer**. It never writes back to source systems.

```
connectors/
  crm/        Zoho CRM · Salesforce
  erp/        Microsoft Dynamics AX / D365
  cmms/       Fiix · MaintainX
  external/   FRED (Federal Reserve) · ABI · LME (London Metal Exchange)
```

All connectors normalize source-specific fields to a canonical schema using a configurable field mapper. New connectors implement a two-method contract: `fetch_work_orders()` and `fetch_assets()` for CMMS, `fetch_commercial_events()` for CRM, `fetch_operational_metrics()` for ERP.

---

## File upload and memory

Operational data that doesn't live in any connected system — weekly order intake, capacity plans, labor utilization reports, budget vs actual spreadsheets — can be uploaded as Excel or CSV. The platform parses, versions, and stores this data in persistent memory. The Intelligence Chat and the exploratory agent both have access to uploaded file context alongside system data.

---

## Intelligence agent

A nightly exploratory agent runs four bounded analytic procedures across all connected data:

1. **Anomaly scan** — metric values more than 2 std devs from rolling mean not caught by standard signals
2. **Cross-system correlation** — patterns spanning CRM + ERP + CMMS simultaneously
3. **Trend acceleration** — signals moving faster than their z-score indicates
4. **File memory reconciliation** — uploaded spreadsheet data vs system record discrepancies

Every finding is recorded as a typed `IntelligenceObservation` with structured evidence fields — observation type, severity, confidence score, source systems, affected entities, supporting signal IDs, supporting metric values, and observation text. The LLM narrates from structured evidence. It does not determine what is significant.

If nothing clears the evidence threshold, zero observations are written. The agent does not invent findings.

---

## CASA governance

Every agent action in Huckleberry passes through the [CASA Runtime](https://github.com/The-Resonance-Institute/casa-runtime) before execution. CASA (Constitutional AI Safety Architecture) is a deterministic pre-execution governance gate — not a safety layer, but a structural access control system.

Every action is described as a 9-field Canonical Action Vector and evaluated against a constitutional graph. The gate returns ACCEPT, GOVERN, or REFUSE before any action executes. Every verdict is recorded to an append-only audit table.

CASA is covered by USPTO Provisional Patent #63/987,813.

---

## Decision ledger

The Decision Ledger is the most strategically valuable component of the platform. It is an append-only record of every leader decision, enforced at three levels: PostgreSQL trigger, application model, and integration tests.

Every entry captures the prediction and simulation that drove the decision, a signal snapshot at decision time, the action taken, and the outcome classified at T+30/60/90. Over time, the ledger builds an institutional memory of signal state → decision → outcome that no other system captures.

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
18 signal types
6 connector types
6 MWAA DAGs
```

The test suite enforces architectural constraints: every new signal type must have a polarity entry, every model must be registered in the database metadata, the Decision Ledger append-only constraint is verified at the trigger level.

---

## Daily briefing

Every morning, senior leaders receive an HTML email briefing with:

- Signal summary — direction and z-score for all active signals
- Active predictions — what the system expects in the next 30-90 days
- Scenario analysis — financial outcomes for each response path
- Intelligence observations — cross-system findings from the nightly agent
- Decisions required — adverse predictions awaiting a leadership response
- Recent outcomes — how prior predictions performed at T+30/60/90

---

## Vertical focus

Built for industrial manufacturing — glass fabricators, building materials companies, HVAC distributors, aluminum processors, steel service centers. The signal library, prediction types, and scenario financial models are calibrated for this vertical's cost structure and operational patterns.

Configurable for adjacent verticals. The canonical data model, signal framework, and governance layer are vertical-agnostic.

---

## Demo

The live demo runs against synthetic data for a fictional glass and aluminum fabricator — Meridian Glass & Aluminum — with three facilities (Atlanta, Charlotte, Memphis). It shows the full platform surface: all 18 signals, active predictions with scenarios, intelligence observations, facility drill-down, budget tracking, and the Intelligence Chat.

**[→ Launch demo](https://demo.huckleberry.ai)**

---

## Contact

Built by [The Resonance Institute, LLC](https://theresonanceinstitute.com).

For enterprise pilot inquiries or acquisition discussions:
**[contact@theresonanceinstitute.com](mailto:contact@theresonanceinstitute.com)**

---

*Huckleberry platform code is proprietary. The connector framework in this repository is open for community contributions. The signal engine, prediction engine, simulation engine, decision ledger, and intelligence agent are maintained in a private repository.*

*CASA architecture covered by USPTO Provisional Patent #63/987,813. © 2026 The Resonance Institute, LLC.*
