# Obseil - expansion roadmap

> Living document. Phases 1-10 built the MVP and are recorded in
> [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). This document plans
> everything after it: the features that take Obseil from a file-analysis tool
> to a continuous data quality platform, the order they arrive in, the seams
> each one uses, and the documentation each one owes.
>
> **Revision 2.** Re-sequenced around the product position in §2. The first
> revision ordered phases by technical dependency, which is the wrong spine for
> an open-source tool - it front-loads invisible plumbing and delays the point
> at which anyone would adopt it. §3 records what changed and why.

Nothing here requires a rewrite. That is not a happy accident - the MVP was
built with these seams in place, and each phase below names the one it uses.

---

## Contents

1. [Where the MVP ends](#1-where-the-mvp-ends)
2. [Product position and the ordering principle](#2-product-position-and-the-ordering-principle)
3. [What changed from revision 1](#3-what-changed-from-revision-1)
4. [Principles that do not change](#4-principles-that-do-not-change)
5. [The LLM boundary](#5-the-llm-boundary)
6. [The waves](#6-the-waves)
7. [Phase detail](#7-phase-detail)
8. [The scoring model has to be versioned](#8-the-scoring-model-has-to-be-versioned)
9. [Documentation plan](#9-documentation-plan)
10. [Testing strategy as the platform grows](#10-testing-strategy-as-the-platform-grows)
11. [Risk register](#11-risk-register)
12. [Non-goals](#12-non-goals)

---

## 1. Where the MVP ends

Obseil today answers *"can I trust this file?"* well. It has four structural
limits, and every feature in this roadmap follows from removing one of them.

| Limit | What it means today | Removed in |
| --- | --- | --- |
| **Quality is defined by us** | Thirteen fixed detectors; a user cannot say what *their* data means | Wave 1 |
| **The unit of work is an uploaded file** | Quality can only be assessed on bytes a human carried to the browser | Wave 2 |
| **The unit of time is a single run** | Nothing watches anything; history exists but nothing acts on it | Wave 3 |
| **The unit of ownership is one person** | `projects.owner_id`, one reviewer per finding | Wave 6 |

The order of those rows is the change in this revision. Revision 1 removed them
in dependency order, which put the file → source transition first. Dependency
order is not adoption order.

---

## 2. Product position and the ordering principle

Written down because it is now the tie-breaker for every sequencing question
below, and because a roadmap whose priorities cannot be checked against a stated
position is just a list.

> Obseil is for **real data teams managing warehouses** who need fast, reliable
> data quality validation **without heavy enterprise bloat**. It is
> **open-source first**, to drive bottom-up adoption in developer communities,
> and it doubles as a **high-signal demonstration of production-ready data
> platform architecture**.

Four consequences, and they mostly agree with each other:

1. **Bottom-up adoption has a specific shape.** A developer finds the repo, runs
   it in minutes, points it at a database they already have, catches something
   real, puts it in CI, and tells a colleague. Nobody in that chain is evaluating
   SSO. The ordering principle follows directly:

   > **Every phase is judged on how much it shortens the path from `git clone`
   > to "this caught something real in my data".**

2. **"Without heavy enterprise bloat" is a positioning statement, not a
   deferral.** SSO, SAML, SCIM, organisations, billing, quotas, usage metering
   and compliance reporting move out of the roadmap and into
   [non-goals](#12-non-goals). That is a deletion, not a reordering. If
   commercial intent firms up they come back, and §12 says what it would cost.
3. **Self-hosting credibility is not bloat.** The known security gaps - token
   revocation, the `localStorage` trade-off, the single-process rate limiter -
   matter *more* for a tool people run themselves than for a SaaS. Those stay, as
   hardening (phase 28), framed as what makes self-hosting trustworthy.
4. **The showcase and the product want the same things.** The phases that
   demonstrate real engineering judgement - the queue, pushdown profiling, the
   incident model, the metric store - are also the phases a data team needs.
   Where they diverge, the product wins; it diverges less often than expected.

**Capacity assumption:** solo, evenings and weekends, so roughly 8-12 focused
hours a week. Every phase below is cut into **slices sized to one week**, each
one independently shippable. One slice per phase is marked ★ as the one that
delivers most of the phase's value, so a phase can be stopped at 60% without
leaving anything half-built.

---

## 3. What changed from revision 1

Recorded rather than silently overwritten, because the reasoning is the useful
part and two of these are reversals.

| Change | Why |
| --- | --- |
| **The rule engine moved from phase 17 to phase 11** | It is the shortest path to "this caught something real in *my* data", it needs no new infrastructure, and it rides the existing `QualityDetector` ABC. It was buried behind six phases of plumbing for no reason other than dependency tidiness |
| **The CLI moved from phase 26 to phase 12** | For bottom-up adoption the CLI is not an ecosystem nicety, it is the adoption vector. `obseil scan` exiting non-zero in CI is what turns a one-off audit into something a team keeps paying for |
| **Background execution moved from phase 11 to phase 14** | Reversal. It is invisible to users and shortens nobody's path to value. A synchronous scan is fine for a CLI run in CI, which can wait 30 seconds. It becomes necessary the moment real warehouse tables arrive, so it lands immediately before them - not six phases early |
| **Warehouse connectors narrowed to PostgreSQL only** | Per the "files now, one connector soon" decision. PostgreSQL is nearly free - `sqlalchemy` and `psycopg` are already dependencies - and it proves the `SourceConnector` seam honestly. Snowflake and BigQuery are deferred until a user asks |
| **Multi-user demoted from phase 13 to phase 26** | A single data engineer self-hosting needs no RBAC. Nothing in the adoption chain touches it |
| **"Add `organisation_id` now" withdrawn** | Reversal. Revision 1 argued for the hedge before data existed. With commercial intent genuinely undecided that is speculative schema. The real hedge already exists and is free: every query funnels through the ownership choke point, so a later tenancy migration has exactly one place to change. The choke point *is* the hedge |
| **Enterprise auth and tenancy deleted, not deferred** | Per the stated position. Split: the enterprise half to non-goals, the hygiene half into phase 28 |
| **Executive dashboards deleted** | Org-level scorecards are bloat for a team-sized tool. The one genuinely honest metric in that phase - monitoring **coverage** - folds into phase 19 instead |
| **Governance narrowed to PII masking** | Classification that masks values in previews, reports and prompts is useful to a data team. Retention policy engines and DPA inventory reports are compliance theatre at this size |
| **A doc-ABC agreement test added** | Prompted by the `fit_predict` bug found while writing revision 1 (see §9). Four more ABCs are coming; the same error will recur |

---

## 4. Principles that do not change

Inherited from the MVP, and binding on every phase below. These are why Obseil
is worth extending rather than replacing.

1. **A rule is used wherever a rule is correct.** A null is a null. No phase
   below replaces a deterministic check with a model.
2. **A model is used only where no rule can answer.** It must earn its keep
   against the simplest statistic that could work, and the comparison goes in
   `METHODOLOGY.md`.
3. **Everything explains itself.** Every finding answers all five questions
   (what, where, why it matters, how it was detected, what to do). Every number
   returns its derivation.
4. **Silence on clean data is an assertion, not an aspiration.**
   `clean_transactions.csv` producing zero rule findings is a test. Its
   generalisation - *a stationary source produces zero findings run after run* -
   is the headline test of Wave 3.
5. **Every threshold is a named constant with its reasoning beside it.**
6. **Approximation is always disclosed.** The MVP says so when it sampled.
   Pushdown profiling and approximate distinct counts inherit that obligation.
7. **Routes stay thin, and authorisation stays in the choke points.** Ownership
   checks funnel through the service-layer helpers and return 404, never 403.
8. **Documentation ships with the feature.** A phase is not done until its docs
   land. The repo already behaves this way; the volume of new surface is the
   reason to write it down.

Two additions the MVP did not need, which continuous operation makes essential:

9. **Determinism is a product feature.** A monitor that changes its mind
   without the data changing is a bug, not noise. Re-running a scan on
   unchanged input must produce an identical result.
10. **The model is never the source of truth.** See §5.

---

## 5. The LLM boundary

Obseil is described as AI-powered and must stay honest about what that means.
[`METHODOLOGY.md §1`](METHODOLOGY.md#1-rules-versus-machine-learning) draws a
hard line between rules and ML; an LLM layer needs the same line drawn before a
single prompt is written, because this is the easiest place in the product to
destroy its core promise.

**Where a language model legitimately earns its place:**

| Use | Why a model is the right tool | Phase |
| --- | --- | --- |
| Narrative synthesis | The output genuinely *is* prose. The facts are all precomputed | 25 |
| Natural language → rule | A compiler at authoring time. The rule it emits is reviewed by a human, versioned, then executed deterministically forever | 25 |
| Remediation drafting | Proposes reviewable SQL/pandas with a preview diff; a human applies it | 24 |
| Ambiguous column classification | Suggests, with confidence; a human confirms; the answer is then frozen into a deterministic rule | 27 |
| Hypothesis phrasing | Ranks and phrases candidate explanations that were assembled deterministically, labelled as hypotheses | 21 |

**Where it is forbidden, in any phase:**

- Computing, adjusting or explaining away the quality score.
- Deciding whether a value is null, duplicate, valid or out of range.
- Producing a finding that a rule could produce.
- Sitting in the execution path of a scheduled scan - cost, latency and
  nondeterminism all disqualify it, and principle 9 forbids it outright.

**The grounding contract**, enforced in code and in tests:

- The prompt carries computed facts only: the score derivation, the findings,
  the profile, metric history. **Raw row values are not sent by default**, and
  never for a column classified sensitive (phase 27).
- Deterministic facts are rendered by templates. The model writes only the
  prose that connects them.
- Every generated claim cites the finding or metric it rests on. A sentence that
  cites nothing is dropped before display.
- A numeric-consistency checker extracts every number from the generated prose
  and diffs it against the source facts. A mismatch fails the test suite.
- **The whole layer is optional.** With no provider configured the deployment
  works completely and the narrative surfaces are simply absent - exactly the
  precedent the OAuth buttons already set, where blank credentials mean the
  button is never shown. For an open-source tool this is not a nicety: most
  self-hosters will run it with no API key at all, and that has to be a
  first-class configuration rather than a degraded one.

An `LLMProvider` ABC with a registry, mirroring `StorageBackend`, keeps the
provider swappable. The default implementation targets Claude (a strong model
for narrative, a cheap one for classification); exact model ids and parameters
are pinned at implementation time in `docs/AI.md`, not here, because they date
faster than this document will.

---

## 6. The waves

Eighteen phases, six waves, continuing the MVP's numbering. **Each phase is
independently shippable**, and each is cut into week-sized slices in §7.

| # | Phase | Weeks | Delivers | Needs |
| --- | --- | --- | --- | --- |
| **1** | **Make it theirs** - the adoption unlock | | | |
| 11 | Rule engine core | 4 | Users define what their own data means | - |
| 12 | Quality-as-code, CLI and CI gate | 4 | `obseil scan` fails a build; rules live in git | 11 |
| 13 | Rule builder UI and rule packs | 3 | Authoring without writing YAML | 11 |
| **2** | **Point it at real data** | | | |
| 14 | Background execution | 3 | Scans outlive an HTTP request | - |
| 15 | PostgreSQL source and pushdown profiling | 5 | Quality on tables, not uploads | 14 |
| 16 | Object storage and columnar formats | 3 | Parquet, JSON, S3 | 14 |
| **3** | **Make it watch** | | | |
| 17 | Scheduled monitors | 4 | Freshness, volume, schema drift, on a cron | 14, 15 |
| 18 | Incidents and alerting | 4 | One alert per problem, in Slack | 17 |
| **4** | **Make it smart** | | | |
| 19 | The metric store, drift and coverage | 4 | Distributions over time | 17 |
| 20 | Learned severity and adaptive thresholds | 4 | Per-column normal; the feedback loop closed | 19 |
| 21 | Suggestions, segments and root cause | 4 | *Where* is this coming from, and what should I assert | 19, 11 |
| **5** | **Fit the stack** | | | |
| 22 | dbt integration, lineage and impact | 4 | Obseil in a stack it did not invent | 15 |
| 23 | Cross-dataset rules | 4 | Referential integrity and reconciliation | 11, 15 |
| 24 | Remediation | 4 | Quarantine, clean exports, recipes | 11 |
| **6** | **When users ask for it** | | | |
| 25 | Grounded narrative layer | 4 | The LLM layer, under §5 | 21 |
| 26 | Project members, audit log, service accounts | 4 | More than one human | - |
| 27 | Sensitive data classification and masking | 3 | PII that is actually masked | 26 |
| 28 | Hardening and operability | 4 | What makes self-hosting trustworthy | 14 |

Sixty-nine weeks of weekend slices if every phase is built. That is the honest
number, and it is the whole reason the waves are ordered by value rather than by
architectural tidiness - on this capacity, the ordering decides what exists in a
year, not just when.

The planning horizon that matters is **Waves 1-3: 30 weeks**, or roughly seven
months of weekends. That is what constitutes a product - users define their own
rules, run them in CI, point them at a database, and get alerted when something
breaks. Waves 4-6 are 39 further weeks and are refinement, not viability.

```
   ┌──────────────────────── WAVE 1 - no new infrastructure ─────────────────┐
   │  11 rule engine ──┬──► 12 CLI + quality-as-code + CI gate   ★ adoption  │
   │                   └──► 13 rule builder UI + packs                       │
   └────────────────────────────────┬────────────────────────────────────────┘
                                    │
   ┌──────────── WAVE 2 ────────────▼───────────────────┐
   │  14 background execution ──┬──► 15 PostgreSQL +    │
   │                            │      pushdown         │
   │                            └──► 16 storage/formats │
   └────────────────┬───────────────────────────────────┘
                    ▼
   ┌──── WAVE 3 ──────────────────────────┐
   │  17 monitors ──► 18 incidents+alerts │
   └──────┬───────────────────────────────┘
          ▼
   ┌──── WAVE 4 ──────────────────────────────────────────────────┐
   │  19 METRIC STORE + drift + coverage                          │
   │        ├──► 20 learned severity, adaptive bands              │
   │        └──► 21 suggestions, segments, root cause ──► 25 LLM  │
   └──────────────────────────────────────────────────────────────┘
   ┌──── WAVE 5 ───────────────┐   ┌──── WAVE 6 - on demand ──────┐
   │  22 dbt + lineage         │   │  26 members + audit + keys   │
   │  23 cross-dataset rules   │   │  27 PII masking              │
   │  24 remediation           │   │  28 hardening                │
   └───────────────────────────┘   └──────────────────────────────┘
```

**Where to start: phase 11, slice 2.** The rule engine is the shortest distance
between the MVP and a data engineer saying "it found something our pipeline
missed". It needs no queue, no connector and no new infrastructure, because
`UserRuleDetector` is just another `QualityDetector`. Phase 12 immediately after
it is what makes that stick, because a rule set in git that fails a build is a
habit, and a web page someone visits occasionally is not.

Resist the urge to start with phase 14. It is the most *architecturally*
satisfying phase in the roadmap and it moves nobody closer to adopting the tool.

---

## 7. Phase detail

Each entry states the design decision and its reasoning, the seam it uses, the
week-sized slices it breaks into, and what has to be true before it is done.
Acceptance criteria are written to be falsifiable, in the spirit of the MVP's
fixture assertions. ★ marks the slice carrying most of the phase's value.

### Wave 1 - Make it theirs

#### Phase 11 - Rule engine core

The MVP decides what quality means. A platform lets its users say it. This is
the single highest-value phase in the roadmap and it needs no new
infrastructure, which is why it is first.

**Execution reuses the existing seam.** One `UserRuleDetector` implements the
existing `QualityDetector` ABC and expands the project's active rule set into
findings. User rules then inherit the fail-soft engine, the findings UI, the
triage flow, the score and every report exporter **for free**. That is what the
ABC was for.

**Two traps in the existing code this phase must fix rather than inherit:**

- `FindingType` is a closed, persisted catalogue, so user rules cannot each have
  a member. Add `FindingType.RULE_VIOLATION` plus a `rule_id` column on
  `findings`.
- `FINDING_DIMENSIONS.get(finding.type, QualityDimension.VALIDITY)` silently
  files an unmapped type under Validity. All fourteen current types are mapped,
  so nothing is mispriced today - but user rules have author-chosen dimensions,
  which makes this live. A missing mapping must fail the build.

**Slices**

1. Rule schema (Pydantic), `rules` table, migration `0006`, CRUD API, ownership
   through the existing choke point. No execution yet.
2. ★ `UserRuleDetector` + the six predicates that cover most real use
   (not-null, unique, allowed values, numeric/date range, regex and named
   formats, string length) + `RULE_VIOLATION` + `rule_id` + the dimension
   exhaustiveness test.
3. Cross-column predicates (`A ≤ B`, `if A then B required`) and a sandboxed
   expression evaluator. **Never `eval`** - an AST allowlist, and it is worth
   writing the hostile tests here rather than later.
4. Rule versioning (`rule_version` on findings), fixtures, `RULES.md`.

- **Guardrail** — rule authors choose severity, but dimension caps still apply.
  A user cannot make their own rule worth 90 points.
- **Versioning** — a finding records the rule version that produced it, for the
  same reason findings are recreated per run: history must stay honest when a
  definition changes.
- **Docs** — RULES.md (new): the catalogue, the expression grammar, the
  dimension mapping.
- **Done when** — a rule's preview count matches the finding it later produces
  exactly; disabling a rule removes it from the next run's score without
  rewriting history; the expression evaluator rejects every case in a hostile
  test file; and `clean_transactions.csv` stays silent under the shipped rule
  packs.

#### Phase 12 - Quality-as-code, CLI and CI gate

The adoption vector. A rule set that lives in the user's repository, applied by
a CLI, gating a pull request.

**`obseil scan` exits non-zero on new critical findings.** That single behaviour
is what converts Obseil from a tool someone visits into infrastructure a team
depends on, and it is the thing to build before anything else in this wave.

**Auth is the dependency people miss.** A CLI in CI cannot use a password or a
30-minute JWT. Full service accounts with RBAC are phase 26 and far too heavy
here, so this phase ships the minimum that is actually needed: a **personal
access token** - long-lived, scoped to its owner's existing permissions, stored
as a hash, revocable, created from a settings page. That is a small table and
one dependency, not an identity system.

**Packaging note:** the backend distribution is `obseil-backend`, so the CLI
wants its own thin package rather than a console script hanging off the API
server. It only needs `httpx`, which is already a dependency - a CLI that talks
HTTP to a deployment is correct here, and one that imports the pipeline directly
would quietly couple the two forever.

**Slices**

1. `obseil.yml` schema, parser, and `obseil rules apply` (diff then push).
   Round-trips with the phase 11 API.
2. Personal access tokens: table, hashing, creation and revocation UI, bearer
   acceptance alongside JWT.
3. ★ `obseil scan` - run, poll, render findings to a terminal, and exit
   non-zero on a configurable severity threshold. Plus `--format json` for
   other tools to consume.
4. A GitHub Action wrapping the CLI, posting a quality diff as a PR comment, and
   dogfooding it in this repo's own CI against a sample dataset.

- **Docs** — API.md (new): CLI reference, `obseil.yml` reference, a CI recipe.
  README gains a quickstart that reaches a failing build in under ten minutes,
  because that is the artefact that drives bottom-up adoption.
- **Done when** — the same rule file produces identical findings through the UI
  and the CLI; the CLI gates a pull request **in this repo's own CI**
  (dogfooding is the test); a revoked token stops working immediately.

#### Phase 13 - Rule builder UI and rule packs

Authoring for people who will not write YAML, and a cure for the blank page.

**Preview against current data before saving is not optional.** A rule you
cannot test before enabling is a rule that will page someone at 3am for nothing.

**Slices**

1. Rule list, create and edit forms per predicate type, wired to phase 11's API.
2. ★ Live preview: run the draft rule against the latest analysis and show the
   row count and sample rows it would flag, before saving.
3. Rule packs - curated starters (PII presence, currency sanity, date sanity,
   retail and finance) - plus one-click apply and the `screenshots.spec.ts`
   additions that keep README honest.

- **Done when** — a rule authored in the UI and the same rule in `obseil.yml`
  are byte-identical after a round trip; the preview count equals the finding's
  count on the next run.

### Wave 2 - Point it at real data

#### Phase 14 - Background execution

Move analysis behind a queue so it stops being bounded by an HTTP request.
Deliberately *not* first: it is invisible, and a synchronous scan is fine for
Wave 1. It is necessary now, because warehouse tables are about to arrive.

The split this needs **already exists**: `dataset_service` stores the file, then
calls the pipeline. The queue boundary goes between those two statements, and
the worker calls the same `run_analysis`. The boundary cannot be drawn finer -
`AnalysisResult` carries the loaded `DataFrame`, which cannot cross a queue - so
the worker owns the whole pipeline. That is the correct shape anyway.

The status enums are **already async-shaped**: `DatasetStatus.ANALYZING`,
`AnalysisStatus.RUNNING` and `error_message` exist today; they just never dwell
in those states for long.

**Queue choice: a PostgreSQL job table using `SELECT … FOR UPDATE SKIP LOCKED`,
not Celery + Redis.** PostgreSQL is already a hard dependency and Redis would be
a new operational surface for no capability gain at this scale; enqueueing in the
same transaction as the dataset insert makes "job queued but dataset missing"
impossible; and the job table doubles as the run-history surface the UI needs
anyway. For a self-hosted open-source tool, *one fewer service in
`docker-compose.yml`* is a feature in itself. Celery remains the escape hatch -
the worker entry point is one function.

**Slices**

1. `analysis_jobs` table, enqueue in the dataset transaction, a worker loop with
   `SKIP LOCKED`, and the Docker Compose worker service.
2. ★ Idempotency and failure handling: the worker creates the `DatasetAnalysis`
   row first and keys the job on `analysis_id` so a retry replaces that run; a
   stale-lock reaper fails jobs whose worker died. This slice is the one that
   decides whether the queue is trustworthy.
3. `202` + status endpoint, TanStack Query `refetchInterval` while running,
   progress stage and percent, and re-measured ceilings.

- **Consequence to re-measure** — `profile_sample_rows` (50,000) and
  `max_analysis_rows` (1,000,000) were derived *under the inline constraint*.
  Re-derive both and update [`PERFORMANCE.md`](PERFORMANCE.md).
- **Docs** — OPERATIONS.md (new): running workers, queue depth, stuck jobs.
- **Done when** — a 500,000-row file completes without an HTTP timeout; killing
  a worker mid-analysis leaves that analysis `failed` with a message and never
  `running` forever; re-running an identical file produces an identical score.

#### Phase 15 - PostgreSQL source and pushdown profiling

The transition that changes what the product is - scoped, per the "one connector
soon" decision, to **PostgreSQL only**. `sqlalchemy` and `psycopg` are already
dependencies, so the connector itself is nearly free; the real work is the
execution strategy, and that work is what makes Snowflake a week rather than a
month later.

A `SourceConnector` ABC mirroring the existing storage and reader seams:
`test_connection`, `list_tables`, `schema`, `sample`, `profile_pushdown`.

**The central decision: push computation to the warehouse.** A hundred-million
-row table cannot come into pandas, so profiling needs two strategies -
in-process (files, small tables) and SQL pushdown. Most statistics are
expressible in SQL: counts, nulls, distinct, min/max/mean/stddev, approximate
quantiles, top-k. Some are not cheap (exact duplicate rows). One is not
expressible at all: Isolation Forest needs rows, so it runs on a bounded, seeded
reservoir sample and **says so**, exactly as `profile_sample_rows` already does.

Principle 6 then binds: an approximate distinct count is **labelled approximate
in the UI**, not quietly rounded.

**The `Dataset` model has to widen.** Today a dataset is an uploaded file with a
`storage_key` and a `checksum_sha256`, and it is immutable - which is what makes
version-to-version comparison honest. A table-backed dataset has neither and
changes underneath you. Add a `source_kind` discriminator
(`upload` | `table` | `query`) and make storage and checksum nullable, rather
than building a parallel model - every downstream object already keys off
`dataset_id`, and duplicating that graph would be a permanent tax. Replace the
lost immutability with snapshot semantics: each scan records the schema
fingerprint and row count it observed. Losing "the dataset never changes" is
precisely what Wave 3 exists to handle.

**Slices**

1. `data_sources` table with envelope-encrypted credentials, the
   `SourceConnector` ABC, PostgreSQL implementation, test-connection and
   table-browse UI.
2. `source_kind` on `Dataset`, nullable storage and checksum, the migration, and
   scanning a table by pulling it into pandas (correct for small tables, and it
   proves the path end to end).
3. ★ The `ProfilingStrategy` seam and SQL pushdown for the statistics that
   express cleanly. This is the slice that makes the phase worth doing.
4. Reservoir sampling for the ML stage, approximate-metric labelling in the UI,
   and the file-versus-table equality test.
5. Security hardening: read-only credential enforcement, host allowlist,
   statement and connection timeouts, identifier quoting, and the new
   SECURITY_REVIEW section.

- **Security** — this is a credential store and an SSRF surface. It gets its own
  SECURITY_REVIEW section, not a footnote.
- **Cost control** — scan budgets and a query cost ceiling. A quality tool that
  quietly runs an expensive warehouse query gets switched off once.
- **Docs** — CONNECTORS.md (new): the support matrix, which statistic is
  computed where, which are approximate, and the grants PostgreSQL needs.
- **Done when** — the same logical data profiled as a CSV and as a PostgreSQL
  table produces the **same profile**, within a documented tolerance for the
  metrics that are approximate by construction.

#### Phase 16 - Object storage and columnar formats

An `S3Backend` on the existing `StorageBackend`, plus the formats real data
arrives in. Parquet matters more than S3 to this audience.

One real friction point, worth naming rather than discovering:
`StorageBackend.local_path()` returns `None` for an object store, but
`DatasetReader.load()` takes a `Path`. **Take the temp file first** - pandas
reads a path far more efficiently (the `local_path` docstring says exactly
this), the temp file's lifetime belongs to the worker, and the reader interface
stays untouched. Widen the interface later, when Parquet row-group pushdown makes
downloading whole files wasteful.

**Slices**

1. ★ Parquet and JSON/NDJSON readers plus `.gz`/`.zip` handling, on the existing
   `get_reader` registry. Highest value in the phase: Parquet is what a data team
   already has lying around.
2. Profiling from Parquet footer metadata - per-row-group min/max/null counts
   mean part of the profile is free, with no scan.
3. `S3Backend`, `storage_backend` config widening, presigned multipart upload so
   the 50 MiB ceiling can go.

- **Done when** — every sample fixture scores **identically** through the local
  and S3 backends (the assertion the MVP already makes between PostgreSQL and
  SQLite), and a Parquet and a CSV of the same data produce identical profiles.

### Wave 3 - Make it watch

#### Phase 17 - Scheduled monitors

The queue from phase 14 plus a due-monitor sweeper. No new infrastructure.

**Three new check families that only exist in time:**

- **Freshness** — `max(timestamp)` against now and against expected cadence.
  Configured here; learned in phase 20.
- **Volume** — row count against recent history, absolute and relative bounds.
- **Schema** — columns added, removed or retyped since the last run. A
  deterministic diff. There is no reason for a model to be near this.

**A monitor must not alert on its first run.** With no history there is no
evidence, and an alert without evidence teaches users to ignore alerts. New
monitors spend a stated number of runs in a visible learning state, and backfill
from prior analyses where any exist.

**Slices**

1. `monitors` table, cron parsing, the due-monitor sweeper on the phase 14 queue,
   enable/disable UI.
2. ★ Freshness and volume checks with the learning period and backfill. The two
   checks a data team actually wants, plus the discipline that stops them being
   noise.
3. Schema-diff checks and the new score dimensions (see §8 - change the
   arithmetic once, deliberately).
4. Synthetic multi-run fixtures and the determinism test.

- **Docs** — MONITORING.md (new): schedules, check semantics, learning period.
- **Done when** — a monitor on an unchanged table produces **zero** findings run
  after run (principle 9, made testable); a deliberately late fixture fires
  exactly one freshness finding; a monitor in its learning period fires none.

#### Phase 18 - Incidents and alerting

This phase introduces one genuinely new concept, and it is the conceptual leap of
Wave 3.

A **finding** belongs to one analysis and is recreated every run - by design,
because a finding describes what a specific run saw, and carrying one forward
would make history dishonest. That design is correct and must not change. But it
means a table broken for nine days produces nine unrelated findings and, naively,
nine alerts.

An **incident** is therefore a separate, longer-lived object: it opens when a
condition first fails, stays open while it keeps failing, and closes when it
passes again. Findings remain immutable per-run evidence; incidents are what
humans work.

**Alert once per incident**, then only on escalation or resolution. Alert fatigue
is the most common reason monitoring tools get switched off, so suppression
belongs in the core model, not in a later settings page.

**Slices**

1. `incidents` table, fingerprinting (monitor + check + column + scope), open and
   close transitions driven by run outcomes, and the link table to evidencing
   findings.
2. ★ Incident inbox UI: open / acknowledged / resolved / muted, assignment,
   and the timeline of runs that evidence it. The incident model is worth little
   until there is a place to work it.
3. The `AlertChannel` ABC with a registry mirroring `ReportExporter`, plus Slack
   and a generic HMAC-signed webhook. Slack first - that is where data teams are.
4. Subscriptions per project, dataset and severity; digest versus immediate;
   delivery retry with backoff and a dead-letter.

- **Docs** — MONITORING.md: lifecycle, fingerprinting, suppression semantics.
- **Done when** — a condition failing on five consecutive runs produces **one**
  incident and **one** alert; recovery sends exactly one resolution notice; a
  muted incident sends nothing; a redelivered webhook is detectably a duplicate.

### Wave 4 - Make it smart

#### Phase 19 - The metric store, drift and coverage

The MVP has no notion of a distribution over time. This phase builds the
substrate for that, and **the substrate is the most leveraged artefact in the
roadmap**: phases 20, 21 and 25 all read from it. Design it deliberately.

- **The metric store** — `metric_observations(dataset_id, column, metric, value,
  observed_at, run_id)`. Long and narrow, indexed on
  `(dataset_id, column, metric, observed_at)`. Every scan writes its statistics
  here.
- **Tests** — PSI and KL for binned and categorical distributions,
  Kolmogorov-Smirnov for continuous, chi-square for category frequency, plus
  plain mean / stddev / null-rate shift. Each with a published threshold, and
  each honest about provenance: the conventional PSI bands (0.1 moderate, 0.25
  significant) are **conventional, not derived here**, and METHODOLOGY must say
  so rather than implying they were measured.
- **Choosing the reference window is the hard part**, and a drift finding that
  does not say what it drifted *from* is useless. Support a blessed fixed
  baseline, a trailing window, and same-period-last-year; default to trailing;
  record which was used in the finding itself.
- **Seasonality** — a naive trailing window alerts every Monday. Learned
  seasonality is phase 20; this phase ships a day-of-week-aware trailing window
  and **writes the limitation down** rather than shipping a known
  false-positive generator quietly.
- **Coverage** — the one genuinely honest aggregate, salvaged from the executive
  dashboard that §3 deleted: what fraction of a project's datasets are actually
  monitored. A tool reporting an average score of 98 across 4% of a warehouse is
  lying by omission, and coverage belongs on the same screen as the score.

**Slices**

1. ★ The metric store: table, indexes, and writing every scan's statistics into
   it. Nothing user-visible, and everything downstream depends on getting the
   shape right.
2. Reference-window machinery and the first two tests (null-rate and mean shift).
3. PSI, KS and chi-square, with thresholds and provenance in METHODOLOGY.
4. Trend charts on the existing Recharts components, plus the coverage metric.

- **Done when** — a stationary fixture produces zero drift findings across 30
  synthetic runs; an injected 20% mean shift is caught within one run; a
  weekly-seasonal fixture produces no Monday finding.

#### Phase 20 - Learned severity and adaptive thresholds

Where the intelligence claim gets earned, using data the MVP already collects.
`FindingFeedback`'s docstring says its verdicts are "the training signal for a
future feedback loop". This is that loop.

Two mechanisms, both deliberately simple:

1. **Learned severity and suppression.** Per `(project, finding type, column)`,
   count `valid_issue` against `false_positive`. Past a confidence threshold -
   a Wilson lower bound, not a raw ratio - adjust severity or suppress. **This is
   a counting rule, not a model.** On tens of labels a classifier would be less
   explainable and no more accurate, and principle 2 forbids reaching for one
   that does not earn its keep.
2. **Adaptive thresholds.** Learn each column's own normal null rate, range,
   cadence and volume from its history and judge it against *that* instead of a
   global constant. This is what makes a platform feel intelligent: the MVP's
   global thresholds are necessarily conservative, because they must be right for
   every dataset at once.

**Guardrails** — never silently learn away a critical finding; never learn from
fewer than a stated number of observations; always show the learned band and let
a human pin it; version bands and record which band a finding was judged against.
**Always show the reason**: "suppressed because you marked this a false positive
7 of 8 times", with one-click undo. A suppression a user cannot see or reverse is
indistinguishable from a bug.

**Slices**

1. Feedback aggregation and the Wilson bound, surfaced read-only first - show
   what *would* be suppressed before suppressing anything.
2. ★ Adaptive per-column bands for null rate, range and volume, with the
   learned band visible and pinnable.
3. Severity adjustment and auto-suppression with the reason string and undo.
4. Seasonal-naive or Holt-Winters baselines for volume and freshness, with
   prediction intervals. The deliberate choice of an inspectable forecaster over
   a black box belongs in METHODOLOGY beside the Isolation Forest reasoning.

- **Done when** — replaying a fixture's history produces stable bands rather than
  oscillating ones; a planted false-positive pattern is suppressed *after* the
  stated evidence threshold and not before; every adjustment traces to the
  feedback that caused it.

#### Phase 21 - Suggestions, segments and root cause

Three features sharing one substrate, the metric store.

- **Suggested rules.** After a stated number of stable runs, propose the rules
  the data already obeys: *"`order_id` has been 100% unique and non-null across
  30 runs - assert it?"* **Entirely deterministic** - a statement about observed
  history, not a guess. Suggestions land in a review queue; accepting one writes
  a real phase 11 rule. This is also the honest cure for the empty rule builder.
- **Segment analysis** - in practice the most useful diagnostic there is. Quality
  is rarely uniformly bad; it is one region, one source system, one day. Given a
  finding, scan candidate dimension columns for the slice that concentrates it,
  report a lift measure, and guard against spurious slices on high-cardinality
  columns.
- **Root-cause hypothesis ranking.** When a score regresses, assemble what
  changed at the same time: the schema diff, the volume change, an upstream
  incident (phase 22), a deploy marker from a webhook. Rank by evidence and
  **label them hypotheses**. Do not call this root cause analysis - the same
  discipline that stops Obseil claiming to know why a row is anomalous.

**Slices**

1. ★ Suggested rules: the stability criteria, the suggestion queue, and
   one-click promotion into a real rule. Highest value, lowest risk, and it
   closes the loop with phase 11.
2. Segment analysis with the lift measure and the significance guard.
3. Segment UI on the finding detail page.
4. Regression view: assemble and rank the co-occurring evidence.

- **Done when** — a planted single-segment defect is localised to that segment;
  every suggestion generated on a stable fixture is one a human accepts; the
  regression view names the schema change behind a planted regression.

### Wave 5 - Fit the stack

#### Phase 22 - dbt integration, lineage and impact

For this audience dbt is not one integration among many - it is where the
transformations and the documentation already live. Reading a `manifest.json`
gives lineage, model ownership and descriptions in one move, which is far cheaper
than inferring them.

- **Data model** — `lineage_edges(upstream_dataset_id, downstream_dataset_id,
  kind, confidence, source)`, populated from a dbt manifest, an explicit
  declaration in `obseil.yml`, or inference. Column-level where available.
- **Impact analysis** — given a failing dataset, what depends on it. The question
  an on-call engineer actually has, and the main reason lineage is worth building.
- **Catalog, minimally** — owner, tags, domain and a **criticality tier**. The
  tier is not decoration: it routes alerts and decides what pages anyone. Stop
  there; a glossary product is a non-goal.

**Slices**

1. ★ dbt manifest import: models to datasets, lineage edges, owners and
   descriptions. One file, most of the value.
2. Lineage graph UI and the upstream/downstream panel on a dataset.
3. Impact view driven by criticality, plus alert routing by tier.
4. Post-build hook so a dbt run triggers the relevant scans.

- **Done when** — a dbt manifest import reproduces a real project's graph; the
  impact view answers "what breaks if this is wrong" in one click.

#### Phase 23 - Cross-dataset rules

A `QualityDetector` sees exactly one frame. Cross-dataset rules genuinely do not
fit that interface, and smuggling a second dataset through
`DetectionContext.scratch` would be reuse in name only. **This needs a new
interface** - `CrossDatasetDetector`, with its own context holding two or more
resolved datasets and its own registry - run by the engine in a second pass.

Referential integrity is bread-and-butter for this audience, so this is the
phase most likely to be pulled forward on user demand; it sits here only because
Waves 1-4 compound faster.

- **Checks** — referential integrity (orphan keys with examples), cardinality
  relationships, uniqueness across a union, shared-dimension consistency, and
  **reconciliation**: row counts, column sums and per-key differences between a
  source and a target.
- **Reconciliation earns its own UI** - rows only in A, rows only in B, differing
  values per key. For anyone mid-migration or validating an ETL, that single view
  is the reason they adopt the tool.
- **Scale** — when both sides live in the same database, push the comparison down
  to SQL. Across engines, compare **partitioned checksums per key range** rather
  than pulling both sides into memory.

**Slices**

1. The `CrossDatasetDetector` ABC, its context and registry, the second engine
   pass, and a new paired fixture (orders/customers with planted orphans).
2. ★ Referential integrity and cardinality checks - the checks people ask for.
3. Reconciliation computation with same-database pushdown.
4. The reconciliation diff UI.

- **Done when** — planted orphans are found exactly with no false positives on
  the clean pair; two identical tables reconcile to zero differences; a
  same-database reconciliation of two large tables completes by pushdown without
  transferring rows.

#### Phase 24 - Remediation

The platform currently tells you what is wrong and stops. Closing the loop means
writing to someone's data, which is a different risk class - so **the default
output is an artefact, never a mutation**.

- **Quarantine** — a scan splits rows into pass and quarantine; the clean subset
  is exportable, the quarantined set downloadable and re-checkable.
- **Cleaning recipes** — a declarative, versioned, replayable list of transforms
  (trim, cast, normalise case, dedup by key keeping latest, fill from another
  column, drop) with a before/after preview and a row count per step. Applying
  one produces a **new dataset version** rather than mutating in place, which
  preserves the immutability that makes comparison honest.
- **Write-back** — opt-in, explicitly scoped, dry-run first, a separately granted
  write credential, and never the default.

**Slices**

1. ★ Quarantine and clean-subset export. The smallest thing that closes the
   loop, and it needs no new risk model.
2. The recipe schema, the transform catalogue, and replay.
3. Preview with a before/after diff and per-step row counts.
4. Ticket creation (GitHub issues first, given the audience) from an incident,
   carrying the finding evidence.

- **Done when** — a recipe applied to `invalid_values.csv` raises its score by
  the predicted amount; a preview matches the applied result exactly; no code
  path mutates a source without a separately granted write credential.

### Wave 6 - When users ask for it

These four are genuinely demand-driven. Building them before anyone asks is how
a lean tool acquires the bloat §2 rules out - with the exception of phase 28,
which is credibility rather than features.

#### Phase 25 - Grounded narrative layer

The LLM layer, implemented strictly under §5 - written there, ahead of this
phase, on purpose. Highest-visibility phase in the roadmap, which is exactly why
it needs the tightest contract.

**Slices**

1. The `LLMProvider` ABC, registry, config, and absence-by-default. Verify the
   whole app works with no key configured before writing a single prompt.
2. ★ The grounded scan narrative: template-rendered facts, model-written
   connective prose, citations required, uncited sentences dropped.
3. The numeric-consistency checker and the CI evaluation suite against a
   recorded-provider fake. No live calls in CI.
4. Natural language → rule compilation into phase 11's schema, with mandatory
   human review before activation.

- **Docs** — AI.md (new): the boundary, the grounding contract, prompt inputs,
  the evaluation suite, and what is deliberately never sent to a model.
- **Done when** — the deployment is fully functional with no provider configured;
  every generated sentence resolves to evidence; the numeric checker passes on
  every fixture; no sensitive-classified column has ever appeared in a prompt.

#### Phase 26 - Project members, audit log, service accounts

`projects.owner_id` is named that way deliberately, and its docstring predicts
this phase: a `project_members` join table arrives beside it without renaming
anything.

Scoped to what a self-hosting team needs and no further. No organisations, no
SCIM, no invitation workflow engine - see §12.

- **Authorisation** — `get_owned_project` becomes
  `get_accessible_project(…, require=Role.EDITOR)`. It stays **one function**;
  that is the entire point of a choke point. The 404-not-403 convention holds for
  every role.
- **`FindingFeedback`** widens from unique on `finding_id` to
  `(finding_id, user_id)` - again, already called out in its docstring.
- **Audit log** (closes a named known gap) — append-only `audit_events`, written
  through one service, never updated, never deleted, with a stated retention.
- **Service accounts** — phase 12's personal access tokens generalised to
  project-scoped machine credentials with a role. Note the hashing difference:
  bcrypt at cost 12 is right for passwords and far too slow for a credential
  presented on every request, so use a high-entropy key with a SHA-256 digest and
  a lookup prefix, and record the reasoning so it does not read as an
  inconsistency.

**Slices**

1. `project_members`, roles, the `get_accessible_project` rewrite, and the
   `FindingFeedback` migration.
2. ★ The role × endpoint authorisation matrix test. The MVP's 22-endpoint matrix
   becomes a role matrix, and the router walk fails the build on a scoped route
   with no declared role. This slice is what makes the phase safe.
3. Member management UI and per-project role assignment.
4. Audit log table, service and viewer; service accounts generalised from PATs.

- **Done when** — a viewer cannot mutate anything and cannot tell a forbidden id
  from a nonexistent one; every mutating endpoint writes exactly one audit event.

#### Phase 27 - Sensitive data classification and masking

- **Classification** — likely PII by name pattern, value pattern, and checksum
  where one exists (Luhn for card numbers). Deterministic detectors first; an LLM
  suggests only for genuinely ambiguous columns, a human confirms, and the answer
  is frozen into a deterministic rule.
- **Classification must *do* something, or it is decoration.** Once classified:
  samples masked in the UI and reports, the column excluded from LLM prompts
  outright, previews restricted by role, exports flagged.

**Slices**

1. ★ Deterministic classifiers and the `column_classifications` table.
2. Masking enforcement across previews, reports, exports and prompt assembly -
   one choke point, tested from every surface.
3. Review UI for confirming or rejecting classifications, plus LLM suggestion for
   ambiguous columns.

- **Docs** — GOVERNANCE.md (new), scoped to classification and masking.
- **Done when** — a planted PII fixture is fully classified; a classified column
  never appears in an LLM prompt or an unmasked preview for a viewer.

#### Phase 28 - Hardening and operability

Not enterprise features - the opposite. This is what makes a stranger willing to
run your software on their warehouse credentials, which for an open-source tool
is the whole ballgame. Its job is to close every entry in
[SECURITY_REVIEW's known gaps](SECURITY_REVIEW.md#known-gaps) or re-justify it.

**Slices**

1. ★ Token revocation (every token already carries a `jti`, so this is a table
   and a check) and an httpOnly refresh cookie. The two largest named gaps.
2. A shared rate-limit store behind the existing `RateLimiter` interface, and the
   linked-identities settings screen with the last sign-in method protected -
   closing the two remaining auth gaps.
3. OpenTelemetry traces spanning API → queue → worker → source; metrics for scan
   duration, queue depth, alert volume and connector errors.
4. Backup and restore runbook with a **tested** restore, plus circuit breakers
   and a dead-letter queue for connector and alert failures. An untested backup is
   not a backup.

- **Done when** — the known-gaps table contains nothing unaddressed; a restore
  has been performed in a drill and written up; one trace covers a full scan end
  to end.

---

## 8. The scoring model has to be versioned

Several phases add quality dimensions: freshness, volume and schema in 17,
user-defined in 11, drift in 19. The MVP's scoring has two load-bearing
properties that casual addition would quietly break:

- The dimension caps **sum to 120**, deliberately, so a dataset broken in every
  dimension can reach zero, while no single dimension can zero it alone.
- `FINDING_DIMENSIONS.get(finding.type, QualityDimension.VALIDITY)` silently
  files any unmapped finding type under Validity.

Three decisions, taken once rather than nudged per phase:

1. **Group dimensions into families with family-level caps** (integrity,
   timeliness, consistency, distribution, anomaly), so adding a dimension does
   not silently inflate the total available penalty and re-break the arithmetic.
2. **Make the mapping exhaustive**, with a test asserting every `FindingType` has
   an explicit dimension. All fourteen current types are mapped, so nothing is
   mispriced today - but the `.get(…, VALIDITY)` fallback means the fifteenth
   will be, silently, and phase 11 adds rules whose dimension is author-chosen.
   A missing mapping should fail the build, not round to Validity.
3. **Version the scoring model.** Add `score_model_version` to
   `dataset_analyses`. Once a dataset is monitored continuously its score becomes
   a time series, and one that silently mixes two formulas is worse than no
   chart. A trend view must refuse to plot across versions, or backfill, and say
   which it did.

Because phase 11 is now first, **decisions 1 and 2 land in phase 11**, before
there is any history to invalidate. That is a direct benefit of the resequencing:
revision 1 would have changed the scoring arithmetic in phase 15, with four
phases of stored scores already behind it.

Extract the result into `docs/SCORING.md`, leaving
[METHODOLOGY §5](METHODOLOGY.md#5-quality-score) a pointer.

---

## 9. Documentation plan

The MVP's documentation is unusually good, and the volume of surface arriving in
this roadmap is exactly how that erodes. Four documents currently carry
everything; eighteen phases will not fit in them.

For an open-source project the documentation *is* the adoption funnel, so the
README quickstart in phase 12 is a feature with a deadline, not a chore.

### Target `docs/` tree

```
docs/
  ROADMAP.md              this document - the plan and its sequencing
  IMPLEMENTATION_PLAN.md  the MVP, frozen; gains a pointer here
  ARCHITECTURE.md         new - the platform as it becomes; supersedes IMPLEMENTATION_PLAN §2
  DATA_MODEL.md           new - ER diagram and every table's purpose
  METHODOLOGY.md          grows - every new detector, drift test, forecaster
  SCORING.md              new - extracted from METHODOLOGY §5 once versioned (§8)
  RULES.md                new - the rule catalogue and the obseil.yml reference
  API.md                  new - public API, CLI reference, CI recipes
  CONNECTORS.md           new - source matrix, pushdown coverage, approximations
  MONITORING.md           new - monitors, incidents, alerting, suppression
  AI.md                   new - the LLM boundary, grounding contract, evaluations
  GOVERNANCE.md           new - PII classification and masking only
  OPERATIONS.md           new - workers, runbooks, backup and restore
  SECURITY_REVIEW.md      grows - connectors, secrets, PAT handling, LLM data flow
  PERFORMANCE.md          grows - pushdown, queue, re-measured ceilings
  adr/NNNN-title.md       new - one decision record per contested choice
```

**Architecture decision records are the structural addition worth arguing for**,
and doubly so given the showcase goal in §2. IMPLEMENTATION_PLAN's single "key
decisions" table is excellent and will not scale to eighteen phases. Each phase
above contains at least one decision with a real alternative - the PostgreSQL job
table over Celery, the temp file over a widened reader interface, the widened
`Dataset` over a parallel model, the counting rule over a classifier, personal
access tokens over service accounts in phase 12. Those belong in dated, numbered
records that say what was rejected and why. A reader evaluating the architecture
learns more from ten ADRs than from any amount of prose.

### Per-phase documentation debt

Carried in each phase entry under **Docs**. The binding rules:

1. **A phase is not done until its documentation lands.** The repo already
   behaves this way. Say it out loud now that there are eighteen chances to stop.
2. **Every threshold is a named constant with its reasoning beside it**, and
   appears in METHODOLOGY or the focused document that replaces it.
3. **Every approximation is labelled approximate wherever it is displayed** - not
   only where it is computed.
4. **Provenance is stated.** A conventional threshold borrowed from the
   literature (the PSI bands) is marked conventional, not presented as measured
   here.
5. **Screenshots stay generated** by `e2e/tests/screenshots.spec.ts`. Every new
   surface extends that spec, which is what makes it impossible for README's
   screenshots to drift. Do not break that property.
6. **Every new scoped route gets a row in the authorisation matrix test.**
7. **Every deferral goes in a Known gaps table**, with why it is acceptable and
   what would close it.

### Drift found while writing revision 1, and fixed

[CONTRIBUTING.md](../CONTRIBUTING.md) told a contributor adding an anomaly
detector to implement `fit_predict(features) -> AnomalyResult`, but the
`AnomalyDetector` ABC in `backend/app/ml/base.py` declares `detect(features)` -
so following the documentation as written produced a class that could not be
instantiated. The likely origin is `isolation_forest.py`, where sklearn's own
`fit_predict` is called *inside* the implementation. Corrected to `detect`.

Worth noting as the pattern this roadmap is most exposed to: an ABC's method name
appears in exactly one place in the docs and nothing tests that the two agree.
These phases add four more ABCs - `SourceConnector`, `CrossDatasetDetector`,
`AlertChannel`, `LLMProvider` - each with its own contributor walkthrough. **A
doc test that imports each ABC and asserts its abstract method names appear in
CONTRIBUTING** would cost an hour and close the whole class of error. Worth doing
in phase 11, where the first new interface lands.

---

## 10. Testing strategy as the platform grows

The MVP's suite already does two unusually smart things - a fixture whose
*silence* is the assertion, and an authorisation matrix that walks the router so
an uncovered route fails the build. Both generalise, and both need deliberate
extension rather than incidental growth.

| Pressure | Response |
| --- | --- |
| User rules can do anything | A hostile test file for the expression evaluator, written in phase 11 rather than after the first report |
| Monitors must not drift | Generalise the clean-file assertion: a **stationary source produces zero findings across N runs**. Principle 9 as a test |
| Drift and adaptive bands need history | A new fixture family: synthetic **run histories** - stationary, trending, seasonal, late-arriving |
| Cross-dataset rules need pairs | Paired fixtures with planted orphans, plus an identical pair that must reconcile to zero |
| Pushdown could diverge from pandas | The equality assertion: **the same data as a file and as a table yields the same profile**, within a documented tolerance |
| Async hides failures | A deterministic in-process executor for queue tests, plus explicit stuck-job and crashed-worker tests |
| Roles multiply endpoints | The 22-endpoint matrix becomes **role × endpoint**; the router walk fails the build on a scoped route with no declared role |
| The CLI is a second client | Round-trip tests asserting the CLI and the UI produce identical rules and findings |
| LLM output must not drift or lie | No live calls in CI: a recorded-provider fake, an uncited-claim assertion, and the numeric-consistency checker |
| PII must not leak | One masking choke point, asserted from every surface that renders values |
| Docs drift from ABCs | The doc-ABC agreement test described in §9 |
| Performance claims must stay true | The existing `backend/scripts/benchmark_pipeline.py` grows a pushdown-versus-pandas comparison |

---

## 11. Risk register

| Risk | Why it is real | Mitigation |
| --- | --- | --- |
| **Never shipping, because the plan is 68 weeks** | The dominant risk for a solo weekend build, and the reason revision 1's dependency ordering was dangerous | Week-sized slices, ★ markers so a phase can stop at 60%, and value-ordered waves so stopping anywhere still leaves a coherent product |
| **Alert fatigue kills adoption** | Nine alerts for one broken table does it in a week | The incident model and suppression land *with* monitoring (18), not after it |
| **Building Wave 6 too early** | Every lean tool acquires bloat by building for an imagined enterprise buyer rather than an actual user | Wave 6 is explicitly demand-gated; §12 names what is out and what it would cost to bring back |
| **The score becomes incomparable** | Adding dimensions silently changes a number users track | Version the scoring model, and land the arithmetic change in phase 11 before any history exists (§8) |
| **Source credentials are the crown jewels** | A read-only warehouse credential is still a warehouse credential, and connectors are a new SSRF surface | Envelope encryption, read-only grants, host allowlists, timeouts (15), plus revocation and audit (26, 28) |
| **LLM overclaim destroys the core promise** | The product's differentiator is that it never says more than it knows | §5 as a binding contract, uncited claims dropped, numeric checker in CI, absent by default |
| **Pushdown correctness divergence** | Two profiling implementations will disagree eventually, and quietly | The file-versus-table equality assertion as a standing test |
| **The metric store becomes the bottleneck** | Three phases read from it; a narrow choice there is expensive to undo | Design it deliberately in 19, indexed for the queries 20, 21 and 25 will make |
| **Open-source adoption needs more than code** | A good tool with a bad quickstart gets no stars and no users | The phase 12 README quickstart is a deliverable with acceptance criteria: `git clone` to a failing build in under ten minutes |
| **Warehouse cost blowout** | One careless full scan buys an angry email from a finance team | Sampling defaults, query cost ceilings, per-monitor scan budgets (15) |

---

## 12. Non-goals

Deliberate, with reasons - the same discipline as
[IMPLEMENTATION_PLAN §7](IMPLEMENTATION_PLAN.md#7-deliberately-out-of-scope-for-the-mvp).
The first group is new in revision 2 and follows directly from "without heavy
enterprise bloat" in §2.

### Deleted as bloat for this product

| Not building | Why | What it would cost to reverse |
| --- | --- | --- |
| SSO: SAML, OIDC, SCIM provisioning | Nobody in the bottom-up adoption chain evaluates SSO. It is the single most common way a lean tool becomes a slow one | A phase of its own, on top of phase 26. Genuinely needed the first time a company with >200 seats asks |
| Organisations above projects | Speculative schema while commercial intent is undecided. The ownership choke point is already the hedge | One migration plus one changed function, *provided* every query still funnels through the choke point. Keeping that true is the real obligation |
| Billing, quotas, usage metering | Only meaningful for hosted multi-tenant SaaS | Depends entirely on the model; do not pre-build for a business that may not exist |
| Compliance reporting, retention engines, DPA inventories | Compliance theatre at this size. PII masking (27) is the part that genuinely protects users | A GOVERNANCE phase, if a regulated customer ever asks |
| Executive dashboards and org-level scorecards | Bloat for a team-sized tool. The one honest aggregate - monitoring coverage - survives in phase 19 | Small, once the metric store exists |
| Snowflake, BigQuery, Databricks, Redshift connectors | Deferred, not deleted. PostgreSQL proves the seam; the rest are demand-driven | Roughly a week each once phase 15's `ProfilingStrategy` seam exists - which is most of why that seam is built properly |

### Out of scope by product definition

| Not building | Why |
| --- | --- |
| An ETL or transformation tool | Remediation (24) produces reviewable artefacts and new dataset versions. Owning the transformation layer is a different product with different competitors - and dbt already has it |
| A BI or dashboarding tool | Obseil reports on data health, not on the data. Lineage points *at* the BI tool; it does not replace it |
| A general observability platform | Application and infrastructure monitoring is well served. Obseil's scope is the data |
| A full data catalog | Build only the catalog surface quality needs: ownership, criticality, tags, lineage. Not a glossary product |
| Streaming quality | Genuinely different architecture - windowed state, at-least-once semantics, sub-second budgets. Worth doing deliberately later, never by stretching the batch pipeline |
| Auto-fixing production data | A human approves every mutation, every time. The write-back path in 24 is opt-in, scoped and dry-run-first by design |
| Deep learning where a statistic suffices | Principle 2. A model must beat the simplest thing that could work, and show its working |
