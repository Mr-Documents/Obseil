# Obseil - Implementation Plan

> Living document. Records the architecture decisions taken while building the MVP
> and the phase-by-phase delivery order.

## 1. Product

Obseil answers one question about a dataset: **"Can I trust this?"**

A user uploads a CSV/XLSX file into a project. Obseil profiles it, runs a suite of
deterministic quality detectors, runs an unsupervised ML anomaly detector, turns
everything into *findings*, and rolls the findings up into an explainable
**0-100 quality score**. Findings can be triaged (reviewed / ignored / false
positive), analyses can be compared over time, and a report can be exported.

## 2. High-level architecture

```
┌──────────────────────┐        ┌───────────────────────────────────────────┐
│  React + TS (Vite)   │  REST  │  FastAPI                                  │
│  Tailwind, Recharts  │◄──────►│  api/  → schemas/ → services/ → models/   │
│  TanStack Query      │  JWT   │                    ↓                      │
└──────────────────────┘        │           analysis pipeline               │
                                │  profiling → quality → ml → scoring       │
                                └────────────┬──────────────┬───────────────┘
                                             │              │
                                    ┌────────▼──────┐  ┌────▼──────────────┐
                                    │  PostgreSQL   │  │ Storage backend   │
                                    │  (metadata,   │  │ local FS today,   │
                                    │   findings)   │  │ S3-compatible     │
                                    └───────────────┘  │ tomorrow          │
                                                       └───────────────────┘
```

Raw datasets never live in PostgreSQL. Only metadata, profiles, findings and
analysis results are persisted relationally.

## 3. Key decisions (and why)

| Decision | Choice | Rationale |
|---|---|---|
| DB access style | **Synchronous** SQLAlchemy 2.0 + `def` route handlers | The analysis pipeline is CPU-bound (pandas/scikit-learn). Async would not help and mixing sync ML work into an event loop is a common production footgun. FastAPI runs `def` handlers in a threadpool. |
| Primary keys | UUID4 stored as `String(36)` | Non-enumerable IDs in a public API, and portable between PostgreSQL and the SQLite used by the fast unit-test suite. |
| JSON columns | `JSON` with a `JSONB` variant on PostgreSQL | Profiles are nested, schemaless-ish documents. JSONB gives indexing headroom; the plain-`JSON` fallback keeps tests DB-agnostic. |
| Passwords | `bcrypt` directly (no passlib) | passlib is unmaintained and breaks against modern bcrypt releases. |
| Tokens | Short-lived JWT access token + longer-lived refresh token | Persistent auth without long-lived credentials in `localStorage`. |
| Server state on the client | TanStack Query | Replaces a large amount of hand-written caching/invalidation/retry code. Fewer bugs than a bespoke `useApi`. |
| Styling | Tailwind CSS v4 (CSS-first config) | No PostCSS config file; design tokens live in one CSS file as custom properties. |
| PDF | ReportLab | Pure Python - no headless browser or system libraries in the container. |
| Anomaly detection | scikit-learn `IsolationForest` | Genuinely useful unsupervised multivariate outlier detection, cheap to train, no labels required, no deep learning justification. |
| Migrations | Alembic | Required for a real Postgres deployment. |

## 4. Analysis pipeline

```
upload → validate → load (pandas) → profile → quality detectors → ML anomaly
      → findings → quality score → persist → dashboard
```

Every stage is an independently testable pure-ish function operating on a
`pandas.DataFrame`; nothing about the pipeline knows about HTTP or the ORM.

## 5. Rule-based vs ML - the boundary

Deterministic statistics are used wherever the answer is knowable exactly:
missingness, duplicates, constant columns, cardinality, type violations,
univariate outliers (IQR / z-score). These are **quality issues** - they are
facts about the data.

Isolation Forest is used only for the thing rules cannot do: finding rows that
are unusual *in combination across several numeric columns*, where no single
column looks wrong. These are **anomalies** - they are candidates for review,
not facts. The UI and the data model keep the two categories visibly separate.

## 6. Phases

1. Repository, backend skeleton, frontend skeleton, Docker, CI ✅
2. Authentication + Projects
3. Dataset upload + profiling engine
4. Quality detection engine
5. Isolation Forest anomaly detection + quality scoring
6. Dashboard, findings, dataset explorer
7. Analysis history + comparison
8. Report export (PDF / CSV)
9. Testing expansion, E2E, security & performance review
10. Final UI/UX polish, documentation, open-source setup

## 7. Deliberately out of scope for the MVP

Teams/orgs, S3, scheduled analyses, DB connectors, LLM explanations,
notifications, drift monitoring. The data model carries an `owner_id` on
projects rather than a `user_id`, and the storage layer is an interface, so
these can be added without a rewrite.
