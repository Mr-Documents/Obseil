# Phase 11 - Rule engine core

> Build plan. Wave 1 of [`../ROADMAP.md`](../ROADMAP.md), and the phase that
> starts it.
>
> Convention established here: one plan per phase at
> `docs/phases/NN-slug.md`, written before the first commit of that phase and
> kept current while it is built. It is a working document and can be deleted
> once the phase ships, though the ADRs it produces are permanent.

**Four slices, roughly four weekends.** Slice 2 is marked ★ as the one carrying
most of the value. The minimum coherent stopping point is **slices 1 + 2**,
which together deliver working user-defined rules; slices 3 and 4 add
expressiveness and honesty, not capability.

---

## 1. Why this phase exists

[`app/quality/detectors/validity.py`](../../backend/app/quality/detectors/validity.py)
states the MVP's position outright:

> The hard part is doing this **without inventing domain rules**. Obseil does not
> know what your columns mean, so it never asserts a business rule it cannot
> justify from the data in front of it.

That is the right call, and it leaves a hole **by design**. Thirteen detectors
can find what is statistically or structurally wrong. None of them can know that
`ship_date` must not precede `order_date`, that `currency` may only be one of
four values, or that `status` of `shipped` requires a tracking number. Those are
facts about the business, not about the data.

Phase 11 is the mechanism by which a user supplies that knowledge, so Obseil can
check it deterministically without ever having guessed it. It completes the
MVP's stated design rather than extending it - which is also why it needs no new
infrastructure and belongs first.

---

## 2. The constraint that shapes the whole phase

Four facts about the existing code, and one conclusion. Getting this wrong is
the main way the phase could go badly, so it is settled here before any code.

1. **`DETECTORS` is a tuple of stateless, import-time instances.**
   [`app/quality/registry.py`](../../backend/app/quality/registry.py) constructs
   every detector at module import. None of them receives per-project state, and
   none of them can - there is no request, session or project in scope.
2. **`run_detectors` already accepts an injection parameter.**
   `run_detectors(frame, profile, detectors=DETECTORS)`.
3. **That parameter is already exercised.**
   `test_engine.py::test_a_failing_detector_does_not_lose_the_others` calls
   `run_detectors(..., detectors=(Exploding(), *DETECTORS))`. Injection is a
   tested, supported capability, not a new seam.
4. **The pipeline is deliberately ORM-free.** `run_analysis(storage_key,
   file_format)` knows nothing about HTTP or SQLAlchemy, which
   [`IMPLEMENTATION_PLAN.md §4`](../IMPLEMENTATION_PLAN.md) names as a property
   worth keeping.

And the decisive one:

5. **`test_engine.py::test_the_clean_dataset_produces_no_findings_at_all`
   asserts `run_detectors(frame, profile_dataset(frame)) == []`** using the
   *default* tuple. Adding a rule detector to `DETECTORS` would either break that
   test or quietly make it meaningless.

> **Decision: a `UserRuleDetector` is never registered in `DETECTORS`.** It is
> constructed per run with that project's rule set and injected through the
> existing `detectors=` parameter. The rule set crosses into the pipeline as
> plain Pydantic objects, never ORM rows, so the pipeline stays ORM-free.

This mirrors a separation the codebase already makes three ways: `FindingDraft`
(domain) / `Finding` (ORM) / `FindingRead` (API). Rules get the same treatment:
`RuleSpec` (domain) / `Rule` (ORM) / `RuleRead` (API).

```python
# app/services/analysis_pipeline.py
def run_analysis(
    storage_key: str,
    file_format: str,
    rules: Sequence[RuleSpec] = (),          # default keeps every caller working
) -> AnalysisResult:
    ...
    detectors = (*DETECTORS, UserRuleDetector(rules)) if rules else DETECTORS
    findings = run_detectors(loaded.frame, profile, detectors=detectors)
```

```python
# app/services/dataset_service.py - analyze_dataset, the single call site
specs = rule_service.active_rule_specs(db, project_id=dataset.project_id)
result = analysis_pipeline.run_analysis(
    dataset.storage_key, dataset.file_format, rules=specs
)
```

The `rules=()` default matters: every existing caller and every existing test
continues to pass **untouched**, and fact 5's assertion stays a live regression
canary rather than being edited to accommodate the new feature.

→ ADR `0001-rules-injected-not-registered.md`.

---

## 3. File manifest

| File | New? | Purpose |
| --- | --- | --- |
| `app/models/rule.py` | new | The `Rule` ORM model |
| `app/models/registry.py` | edit | Import `Rule` so Alembic sees it |
| `app/models/finding.py` | edit | `rule_id`, `rule_version` columns |
| `app/models/dataset.py` | edit | `rule_skip_notes`, `score_model_version` |
| `alembic/versions/0006_rules.py` | new | Table + the three column additions |
| `app/quality/rules/types.py` | new | `RuleSpec`, `RulePredicate` enum, parameter models, `RuleEvaluation` |
| `app/quality/rules/predicates.py` | new | One evaluator per predicate |
| `app/quality/rules/registry.py` | new | Predicate registry, keyed by name |
| `app/quality/rules/expressions.py` | new | The AST-allowlist evaluator (slice 3) |
| `app/quality/rules/detector.py` | new | `UserRuleDetector(QualityDetector)` |
| `app/quality/types.py` | edit | `RULE_VIOLATION`, `USER_RULE`, `FindingDraft.dimension` |
| `app/quality/scoring.py` | edit | Honour an author-chosen dimension; remove the silent default |
| `app/schemas/rule.py` | new | `RuleCreate` / `RuleUpdate` / `RuleRead` |
| `app/services/rule_service.py` | new | CRUD, the ownership choke point, `active_rule_specs` |
| `app/api/v1/routes/rules.py` | new | Five endpoints |
| `app/api/v1/router.py` | edit | `api_router.include_router(rules.router)` |
| `app/api/deps.py` | edit | `OwnedRule` dependency |
| `app/services/finding_service.py` | edit | Persist `rule_id` / `rule_version` |
| `app/services/analysis_pipeline.py` | edit | `rules` parameter, detector injection |
| `app/services/dataset_service.py` | edit | Load specs, pass them, store skip notes |
| `data/generate_samples.py` | edit | `rule_violations_dataset()` + a `GENERATORS` entry |
| `docs/RULES.md` | new | Catalogue, parameters, expression grammar |

Tests are listed in §8.

---

## 4. Slice 1 - Rules as data

**Goal:** a project owner can create, list, read, update and delete rules. None
of them execute yet. Shippable on its own: it is a complete, tested CRUD
resource.

### The `rules` table

```python
class Rule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rules"
    __table_args__ = (
        Index("ix_rules_project_enabled", "project_id", "enabled"),
        UniqueConstraint("project_id", "name", name="uq_rules_project_name"),
    )

    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Null for rules that are not about one column (comparison, expression).
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    predicate: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Predicate-specific configuration, validated by a discriminated union at
    #: the API boundary and again on load. Schemaless in the database, strictly
    #: typed in the application.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    dimension: Mapped[str] = mapped_column(String(24), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Bumped when the rule's *meaning* changes. See slice 4.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

**Why `predicate` + a JSON `parameters` blob rather than a column per predicate
type.** The predicate set will grow, and a wide sparse table would need a
migration for every addition. The precedent already exists and works:
`DatasetAnalysis.profile` is a nested JSON document validated by a Pydantic
model (`DatasetProfile`). Rules use the same shape - a discriminated union on
`predicate` validates `parameters` at the boundary, so the database is permissive
and the application is strict.

→ ADR `0002-rule-parameters-as-json.md`.

**Why a unique constraint on `(project_id, name)`.** A finding's title is derived
from the rule name, so two rules with the same name produce two
indistinguishable findings. Enforced in the database rather than in whichever
code path happens to run - the same reasoning as `uq_oauth_provider_account`.

### Service and routes

Copy the shape of `project_service.py` and `routes/projects.py` exactly:

- `get_owned_rule(db, *, rule_id, user)` joins through `Project` and raises
  `NotFoundError` - **404, not 403**, preserving the convention.
- `create_rule` / `update_rule` (partial, via `model_dump(exclude_unset=True)`) /
  `delete_rule` / `list_rules` / `count_rules`.
- `OwnedRule = Annotated[Rule, Depends(get_rule)]` in `deps.py`, beside
  `OwnedProject`.

| Method | Path |
| --- | --- |
| `GET` | `/api/v1/projects/{project_id}/rules` |
| `POST` | `/api/v1/projects/{project_id}/rules` |
| `GET` | `/api/v1/rules/{rule_id}` |
| `PATCH` | `/api/v1/rules/{rule_id}` |
| `DELETE` | `/api/v1/rules/{rule_id}` |

Validation failures raise `ValidationError` (422), duplicate names
`ConflictError` (409) - both already exist in `core/errors.py`.

### Migration `0006_rules.py`

Revises `0005_oauth_accounts`. Creates `rules`, then adds to `findings`:

```python
with op.batch_alter_table("findings") as batch:        # SQLite-safe, as 0005 did
    batch.add_column(sa.Column("rule_id", sa.String(36), nullable=True))
    batch.add_column(sa.Column("rule_version", sa.Integer(), nullable=True))
    batch.create_foreign_key(
        "fk_findings_rule", "rules", ["rule_id"], ["id"], ondelete="SET NULL",
    )
```

**Why `SET NULL` and not `CASCADE`.** Deleting a rule must not delete the record
of what it once found. A finding is evidence of what a specific run saw, and the
rule being removed later does not unmake that - the same principle that makes
findings recreated per run rather than carried forward.

**Why real columns rather than stuffing the rule id into `details`.** Both need
to be queryable: "show every finding this rule produced" is a UI requirement in
phase 13, and phase 20's learned severity groups feedback by rule.

### Done when

- Full CRUD works and is covered by `tests/api/test_rules.py`.
- A rule belonging to another account returns 404 from every endpoint.
- `tests/api/test_security.py` is updated (see §8) and green.
- Creating two rules with the same name in one project returns 409.
- `alembic upgrade head`, `downgrade`, `upgrade` round-trips, and
  `alembic check` reports no drift.

---

## 5. Slice 2 ★ - Execution and the six predicates

**Goal:** enabled rules run during analysis and produce findings that are
indistinguishable in quality from the built-in ones. This is the slice that
makes the phase worth doing.

### The six predicates

Chosen because between them they cover most of what people actually assert.

| Predicate | Parameters | Violation |
| --- | --- | --- |
| `not_null` | - | value is missing |
| `unique` | `ignore_nulls` | value appears more than once |
| `allowed_values` | `values`, `case_sensitive` | value not in the set |
| `range` | `min`, `max`, `inclusive` | numeric or date outside bounds |
| `pattern` | `regex` **or** `format` | string does not match |
| `length` | `min_length`, `max_length` | string length outside bounds |

`format` is a named shorthand over vetted patterns (`email`, `uuid`,
`iso_date`, `url`, `ipv4`), because a user writing their own email regex will get
it wrong and blame the tool.

### Predicate interface

A `RulePredicate` ABC with a registry, consistent with `QualityDetector`,
`DatasetReader`, `ReportExporter` and `StorageBackend`:

```python
@dataclass(slots=True)
class RuleEvaluation:
    """What one rule found. `mask` is per-row; None for non-row-wise rules."""
    count: int
    mask: pd.Series | None = None
    examples: list[str] = field(default_factory=list)
    #: Set when the rule could not be evaluated at all. Not a violation.
    skipped_reason: str | None = None


class RulePredicate(ABC):
    name: str = "predicate"
    parameters_model: type[BaseModel]

    @abstractmethod
    def evaluate(self, spec: RuleSpec, context: DetectionContext) -> RuleEvaluation: ...
```

The registry gives phase 13's UI a free enumeration of predicates and their
parameter schemas, so the builder form is generated rather than hand-maintained.

### What happens when a rule names a column that is not there

A typo in a column name is the most likely configuration error, and all three
obvious behaviours are wrong in different ways: failing the analysis punishes the
user for a typo, raising a violation is a false positive, and **skipping
silently means the rule never runs and nobody ever finds out** - the worst of the
three.

> **Decision: an unevaluatable rule produces no finding and no score penalty.
> It is recorded on the analysis and surfaced in the UI.**

This follows the precedent already set for the ML stage, whose docstring says a
skip is "a normal outcome, not a failure", recorded in `ml_skipped_reason`. Rules
get the direct analogue:

```python
# app/models/dataset.py - DatasetAnalysis
rule_skip_notes: Mapped[list[Any] | None] = mapped_column(JSONColumn, nullable=True)
```

The dashboard shows "2 rules could not be evaluated" with the reasons. Scoring
never punishes a dataset for a misconfigured rule.

### Findings from rules

`FindingType.RULE_VIOLATION = "rule_violation"` - **one** member, not one per
predicate, because the enum is a closed, persisted catalogue. The predicate lives
in `details`, the identity in `rule_id`.

`DetectionMethod.USER_RULE = "user_rule"`, with
`DETECTION_METHOD_LABELS[USER_RULE] = "User-defined rule"` so the UI never
renders a raw enum (`FindingRead.detection_method_label` depends on that dict).

**The scoring change.** `FINDING_DIMENSIONS` maps one `FindingType` to one
`QualityDimension`, but a rule's dimension is author-chosen per rule. So
`FindingDraft` gains an optional override:

```python
# app/quality/types.py
class FindingDraft(BaseModel):
    ...
    #: Set only by user-defined rules, whose dimension is chosen by the author.
    #: Built-in detectors leave this None and are classified by FINDING_DIMENSIONS.
    dimension: QualityDimension | None = None
```

```python
# app/quality/scoring.py - calculate_quality_score
dimension = finding.dimension or FINDING_DIMENSIONS[finding.type]
```

Note the second change in that line: `FINDING_DIMENSIONS.get(finding.type,
QualityDimension.VALIDITY)` becomes a plain lookup. The silent fallback is
removed, so a future unmapped type raises in development instead of quietly
mispricing the score. `RULE_VIOLATION` is still given an entry (`VALIDITY`) so
the mapping stays total and the exhaustiveness test in §8 needs no exemptions.

Deleting that fallback is safe **today**, and this was checked rather than
assumed: `FindingType` has 14 members, `FINDING_DIMENSIONS` has 14 keys, and
nothing is unmapped. The fallback is currently dead code, which is exactly why it
is safe to remove and why it would have bitten the next person to add a type.

**Guardrail:** authors choose severity, but `DIMENSION_CAPS` still applies, so a
user cannot make their own rule worth 90 points. No new dimensions are introduced
in this phase, so the invariant holds - `sum(DIMENSION_CAPS.values())` is exactly
120.0, verified. Family caps
([ROADMAP §8](../ROADMAP.md#8-the-scoring-model-has-to-be-versioned) decision 1)
are only needed when phase 17 adds freshness and volume.

**Every rule finding must answer all five questions**, because
`test_every_finding_answers_all_five_questions` is parametrised over fixtures and
will cover them. `impact` falls back to a generated sentence when the author
wrote no description, and `recommendation` is generated per predicate. Neither
may ever be empty.

### Done when

- A rule set on a project changes that project's next analysis, and no other
  project's.
- `test_the_clean_dataset_produces_no_findings_at_all` is **still green,
  unedited** - the canary from §2.
- A rule naming a missing column produces a skip note, zero findings and no
  score change.
- A rule's violation count equals the number of rows a hand-written pandas
  expression finds on the same fixture.
- Disabling a rule removes it from the next run without touching stored history.

---

## 6. Slice 3 - Cross-column rules and the expression evaluator

**Goal:** rules that span columns. This slice carries the only real security
risk in the phase, so it is deliberately separate.

### Cross-column predicates

| Predicate | Parameters |
| --- | --- |
| `comparison` | `left_column`, `operator` (`lt`/`lte`/`gt`/`gte`/`eq`/`ne`), `right_column` |
| `conditional_required` | `when_column`, `when_operator`, `when_value`, `then_column` |

Both are null-safe: a null on either side is **not** a violation, and the
finding's `details` says how many rows were skipped for that reason. Silently
treating null as a failure would make these rules fire on incomplete data that
the completeness detectors already report, double-counting the same defect.

### The expression evaluator

`expression` with a single `expression` string, e.g.
`amount > 0 and len(reference) == 8`.

**Never `eval()`, and not `DataFrame.eval()` either** - the latter is more
permissive and more surprising than it looks. Instead:

1. `ast.parse(source, mode="eval")`.
2. Walk the tree against a strict **allowlist** of node types: `Expression`,
   `BoolOp`, `UnaryOp`, `BinOp`, `Compare`, `Name`, `Load`, `Constant`, the
   boolean/comparison/arithmetic operators, and `Call` only for a fixed function
   set (`len`, `lower`, `upper`, `abs`, `isnull`, `notnull`).
3. Reject everything else explicitly: `Attribute`, `Subscript`, `Lambda`,
   comprehensions, `Starred`, f-strings, walrus, and any name beginning with an
   underscore.
4. `Name` nodes resolve **only** to columns present in the frame; anything else
   is a validation error naming the unknown identifier.
5. Evaluate the validated tree with a small recursive interpreter that emits
   vectorised pandas operations.

Two named limits, with reasoning beside them in the house style:

```python
#: Longest accepted expression. Not a security boundary on its own - the AST
#: allowlist is - but a cheap guard against pathological input reaching the parser.
MAX_EXPRESSION_LENGTH = 500

#: Maximum AST depth. CPython's own parser recurses, so deeply nested parentheses
#: can exhaust the stack before any allowlist check runs.
MAX_EXPRESSION_DEPTH = 20
```

Validation happens **at authoring time** (so the API rejects a bad expression on
`POST`/`PATCH` with a message naming the problem) **and again at evaluation
time**, because a rule stored before a predicate changed must not be trusted.

→ ADR `0003-expression-evaluator-allowlist.md`.

### Done when

- `tests/unit/quality/test_rule_expressions.py` - the hostile file in §8 - passes
  in full.
- A `comparison` rule on a fixture with planted violations finds exactly those.
- Null handling is asserted in both directions: nulls are not violations, and the
  skipped count is reported.

---

## 7. Slice 4 - Versioning, fixtures and documentation

**Goal:** the phase becomes honest and documented.

### Rule versioning

`update_rule` compares the **semantic** fields - `predicate`, `parameters`,
`severity`, `dimension`, `column_name` - and bumps `version` when any changed.
Renaming a rule or editing its description does not bump it. Findings record
`rule_version`, so a history that spans a rule change says which definition
judged each run.

Deliberate limitation, stated rather than hidden: the previous definition is not
retained, so you can know a rule differed but not what it was. A `rule_versions`
table would close that and can be added later without changing `findings`. Not
worth the machinery until someone asks.

### `score_model_version`

```python
# app/models/dataset.py - DatasetAnalysis
score_model_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

Cheap now, expensive later -
[ROADMAP §8](../ROADMAP.md#8-the-scoring-model-has-to-be-versioned) decision 3.
Adding the column before there is history avoids a backfill, and phase 17's
dimension changes will bump it. Nothing reads it yet beyond trend charts
refusing to plot across versions.

### Fixture

**The sample datasets are generated, not hand-written.**
`data/generate_samples.py` holds one function per dataset and a module-level
`GENERATORS` dict mapping name to function; `main()` iterates it, builds each
frame from a **fresh `np.random.default_rng(SEED)`** - deliberately, so that
adding a generator cannot change any existing file - and writes
`{name}.csv`. So the work is:

1. Add `rule_violations_dataset(rng)` beside the existing generators, planting a
   known count of violations for every predicate.
2. Register it: `"rule_violations": rule_violations_dataset` in `GENERATORS`.
3. Run `python data/generate_samples.py` and commit the resulting CSV.
4. Document what it contains in `data/samples/README.md`, which is the fixtures'
   record of what *should* be found in each.

Writing the CSV by hand would work exactly once and then drift from the script
that regenerates its siblings - and `tests/fixtures.py` already points users at
that script when a sample is missing.

Per principle 4, the matching assertion is that the **shipped rule packs stay
silent on `clean_transactions.csv`** - the generalisation of the MVP's best test.

### Documentation

- `docs/RULES.md` - the predicate catalogue with every parameter, the expression
  grammar and its allowlist, the dimension and severity model, and the
  unevaluatable-rule semantics.
- The three ADRs named above, in `docs/adr/`.
- `CONTRIBUTING.md` gains an "Adding a rule predicate" walkthrough beside the
  existing detector ones.
- **The doc-ABC agreement test** from
  [ROADMAP §9](../ROADMAP.md#9-documentation-plan): import each ABC, assert its
  abstract method names appear in `CONTRIBUTING.md`. `RulePredicate` is the first
  new ABC, so this is the right moment, and it retro-covers the
  `fit_predict`/`detect` class of error.

---

## 8. Test plan

| File | New? | Covers |
| --- | --- | --- |
| `tests/unit/quality/test_rules.py` | new | Each predicate against a small purpose-built frame, in house style |
| `tests/unit/quality/test_rule_expressions.py` | new | The hostile file, below |
| `tests/unit/quality/test_engine.py` | edit | Injected rule detector; the clean-file canary stays **unedited** |
| `tests/unit/quality/test_scoring.py` | edit | Author-chosen dimension honoured; dimension mapping is total |
| `tests/api/test_rules.py` | new | CRUD, ownership, validation - mirrors `test_projects.py` |
| `tests/api/test_security.py` | edit | See below |

### `test_security.py`, precisely

```python
OWNED_PATH_PARAMETERS = frozenset({
    "project_id", "dataset_id", "analysis_id", "finding_id", "rule_id",   # + rule_id
})
```

Five rows appended to `SCOPED_ENDPOINTS` (the five endpoints in slice 1), a
`_request_body` case so `POST`/`PATCH` on rules carry a valid body and reach the
ownership check rather than 422-ing first, and
`MINIMUM_EXPECTED_ROUTES` raised from **25 to 30**. The router walk then fails
the build if any of the five ships uncovered - which is the mechanism that
caught three untested endpoints during the MVP.

### The exhaustiveness test

```python
def test_every_finding_type_has_a_dimension() -> None:
    assert [t for t in FindingType if t not in FINDING_DIMENSIONS] == []
```

Cheap, and it is what makes removing the silent `VALIDITY` fallback safe.

### The hostile expression file

Each of these must be rejected at authoring time, with a message that does not
leak internals:

`__import__("os").system("...")` · `().__class__.__bases__` ·
`(lambda: 1)()` · `[x for x in range(10)]` · `f"{amount}"` ·
`amount.__class__` · `globals()` · `open("/etc/passwd")` ·
`amount if True else 0` · `(((((...)))))` beyond `MAX_EXPRESSION_DEPTH` ·
a string longer than `MAX_EXPRESSION_LENGTH` · `unknown_column > 1` ·
`1/0` (must be a clean validation error, not a traceback).

---

## 9. Risks specific to this phase

| Risk | Mitigation |
| --- | --- |
| **The expression evaluator is the one genuine security surface added** | AST allowlist rather than any form of `eval`; validation at authoring *and* evaluation; the hostile file is written in the same slice, not later; slice 3 is separable so slices 1-2 can ship without it |
| **User rules could flood the findings list** | Rules are per-project and opt-in, severity is capped by dimension, and phase 13's preview shows the count before a rule is enabled |
| **A misconfigured rule silently never runs** | The skip-note mechanism in slice 2 makes it visible and counted; silence was explicitly rejected as the worst option |
| **Scope creep into phase 13** | The UI, draft preview and rule packs are phase 13. Phase 11 ships API-only, and `obseil.yml` is phase 12 |
| **Removing the `VALIDITY` fallback breaks something unforeseen** | The exhaustiveness test lands in the same commit, so the mapping is proven total before the fallback is deleted |

---

## 10. Explicitly deferred

| Deferred | To |
| --- | --- |
| Rule builder UI, live preview of a draft, rule packs | Phase 13 |
| `obseil.yml`, the CLI, personal access tokens | Phase 12 |
| Custom SQL predicates | Phase 15, once a source connector exists |
| Cross-*dataset* rules (referential integrity) | Phase 23 - needs the `CrossDatasetDetector` ABC, which `QualityDetector` cannot express |
| Suggested rules from observed stability | Phase 21 - needs the metric store |
| Learned severity from rule feedback | Phase 20 |
| Full rule definition history | Not planned; `rule_versions` is the seam if asked for |
