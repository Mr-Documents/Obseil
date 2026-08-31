# Obseil methodology

How Obseil decides what to tell you, and why it draws each line where it does.

The guiding principle throughout: **a detector that fires on everything is as
useless as one that fires on nothing.** Every threshold below is chosen to keep
the clean baseline dataset at zero findings while still catching every defect
deliberately injected into the other fixtures. That property is enforced by
tests, not by intention — see `backend/tests/unit/quality/test_engine.py`.

---

## 1. Rules versus machine learning

Obseil reports two kinds of thing and keeps them visibly apart, in the data
model (`category`), in the API, and in the UI.

| | **Quality issue** (`category: rule`) | **Anomaly** (`category: anomaly`) |
| --- | --- | --- |
| Produced by | Deterministic statistics | Unsupervised model |
| Claim being made | *This is a fact about the data* | *This row is unusual; look at it* |
| Reproducible | Exactly, every run | Yes, given the same seed and data |
| Can be "wrong" | Only if the rule is wrong | Yes — legitimately unusual rows exist |

**Rules are used wherever the answer is knowable exactly.** Counting nulls does
not need a model. Neither does finding duplicated rows, constant columns, or
values outside Tukey's fences. Using ML for any of these would be slower, less
accurate, less explainable, and — the important part — *dishonest about what is
actually being computed*.

**ML is used for the one thing rules cannot do:** finding rows that are unusual
*in combination across several numeric columns*, where every individual value
sits comfortably inside its own column's normal range. See §4.

The `anomalous_transactions.csv` fixture exists to make this concrete: it
contains twelve rows that are implausible in combination, and the entire rule
engine reports **zero findings** on it. That is not a gap — it is the argument
for having an ML component at all.

---

## 2. Profiling

Before anything is checked, every column is profiled.

### Semantic type inference

pandas gives a *storage* dtype. Obseil infers what the column **means**, because
that is what determines which checks are appropriate.

| Inferred type | How it is decided |
| --- | --- |
| `integer` | Numeric dtype, all values whole (a float column of whole numbers counts) |
| `numeric` | Numeric dtype with fractional values |
| `boolean` | Boolean dtype, or a text column whose values are all drawn from a small boolean vocabulary (`true/false`, `yes/no`, `y/n`, `on/off`) |
| `datetime` | Datetime dtype, or ≥95% of text values parse as dates |
| `categorical` | Text with ≤50 distinct values **and** ≤50% distinct |
| `text` | Anything else with values |
| `empty` | No non-null values at all |

Two deliberate decisions:

- **`0`/`1` stays numeric, not boolean.** A 0/1 flag is a numeric indicator, and
  calling it boolean would suppress statistics that are genuinely useful for it.
- **A text column that is ≥95% parseable as numbers is typed `numeric` and
  additionally flagged `is_numeric_like`.** The values are numbers; the storage
  is wrong. Those are two different statements and Obseil makes both.

The categorical rule needs **both** conditions. 40 distinct values in 50 rows is
a small dataset, not a category; 5,000 distinct values in 10,000 rows is not one
either.

### Statistics are type-appropriate by construction

A mean over a categorical column is noise dressed up as insight. Numeric
statistics are attached only to numeric columns, datetime ranges only to
datetime columns, and length statistics only to anything stored as text.

NaN and infinity become `null`, because neither is representable in JSON and an
explicit absence is better than an invalid document.

### Identifying identifier columns

Getting this wrong is costly in both directions: treat a measurement as a key
and every continuous column is reported as a "broken key"; miss a real key and
duplicate identifiers go unreported.

Uniqueness alone cannot separate them — a float measurement is naturally ~95%
distinct, while a genuinely broken key may be only 85% distinct. So two signals
are combined:

1. **Type.** Continuous floats are excluded outright. A key with a decimal point
   is not a thing.
2. **Either near-perfect uniqueness (≥99% distinct), or a name that declares
   intent** (`*_id`, `*_key`, `*_ref`, `uuid`, …) combined with ≥70% distinct.

A column named `transaction_id` is asserting that it identifies a transaction,
so the gap below 100% is exactly the defect worth reporting. A `loyalty_points`
column that happens to be 94% distinct is not making that claim.

*Accepted trade-off:* a badly broken key with an unconventional name and only
~90% distinct values is missed. That is far better than reporting every
continuous column in every dataset as a broken key.

---

## 3. Quality detectors

Every finding answers five questions, and the schema has a field for each:

| Question | Field |
| --- | --- |
| What happened? | `title`, `description` |
| Where? | `column`, `affected_rows`, `sample_row_indices` |
| Why does it matter? | `impact` |
| How was it detected? | `detection_method`, `details` |
| What should I do? | `recommendation` |

### Missing values — `null_count`

Columns below **5% missing are not reported at all**. Every real export has a
few gaps, and flagging them teaches people to ignore findings.

| Missing | Severity | Reasoning |
| --- | --- | --- |
| ≥ 5% | Low | Joins and aggregates no longer cover every row |
| ≥ 15% | Medium | Dropping incomplete rows removes a meaningful share; imputing visibly changes the distribution |
| ≥ 40% | High | Statistics over the remainder describe a subset, not the dataset |
| ≥ 80% | Critical | The column is effectively absent |

A column with **no** values at all is a separate finding (`empty_column`, high):
it is a different problem with a different fix.

### Incomplete rows — `row_completeness`

Rows missing **more than half** their fields. Deliberately separate from the
column check, because a row missing 8 of its 11 fields can sit in a dataset
where no individual column looks bad. These records carry almost no information
but still count towards row totals.

### Duplicate rows — `exact_row_match`

Byte-for-byte repeats across every column. Counted as *repeats*, not
occurrences: three identical rows are two duplicates. All copies including the
first are sampled, because a reviewer needs the original to compare against.

| Duplicated | Severity |
| --- | --- |
| > 0% | Low |
| > 1% | Medium |
| > 5% | High |
| > 20% | Critical |

### Duplicate identifiers — `uniqueness_check`

Repeated values in a key-like column (§2). Row counts are fine; **joins are
not** — a join on this column fans out and silently multiplies rows. Always
high severity for that reason.

### Constant columns — `distinct_count`

One distinct value. **Low severity on purpose**: this is waste, not corruption.
Scoring it harshly would drown out findings that actually corrupt results.

### High cardinality — `cardinality_ratio`

A narrow, specific target: a column that is neither a usable category nor a
usable key — ≥50 distinct values **and** ≥70% distinct, excluding identifiers.

311 distinct customers across 600 transactions (52%) is an ordinary foreign key
and is **not** flagged. A column that is 75% distinct with hundreds of values
usually is free-text entry masquerading as a category — `London`, `london`,
`London ` counted as three.

### Numbers stored as text — `type_inference`

Reported as a *type* problem, not a value problem. Nothing is wrong with the
numbers; everything downstream will sort them alphabetically and refuse to sum
them. Escalated to medium when some values will not convert, because those
become nulls on cast — silently losing rows.

### Negative values — `sign_check`

The hardest detector to do honestly, because Obseil does not know what your
columns mean and must not invent business rules.

**Two independent pieces of evidence are required**, and the finding lists which
applied:

1. Negatives are a small minority (< 5% of the column). A column that is 40%
   negative has a legitimate negative range.
2. **Either** the column name denotes a quantity that cannot be negative
   (`amount`, `quantity`, `age`, `count`, …) **or** the column is integer-valued
   — counts far more often than measurements.

Requiring both keeps a profit-and-loss column from being flagged just because it
happens to be mostly positive. Names like `balance`, `change` and `score` are
deliberately excluded from the vocabulary: negatives are normal for them.

This remains a heuristic, and it is exactly why the false-positive verdict
exists.

### Invalid dates — `date_parsing`

Only runs on columns already inferred to be dates, which requires 95% of values
to parse. That gate is what makes the leftovers meaningful: they are the
exceptions in a column that is otherwise clearly a date. Catches both
unparseable text and impossible dates (`2026-13-45`, `31/02/2026`).

### Empty strings and whitespace — `string_inspection`

Both matter precisely because **pandas does not treat them as missing**. A
column can report as 100% complete while a tenth of its values are `""` or
`"  "`. `London ` and `London` are different values to every join and group-by.

---

### Outlier detection — `iqr`, cross-checked with `z_score`

**IQR (Tukey's fences)** is the primary method: values outside
`[Q1 − 1.5·IQR, Q3 + 1.5·IQR]`. Quartiles are rank statistics, so the fences are
not themselves dragged outwards by the extreme values they exist to find. That
robustness is the whole reason for preferring them.

**Z-score is reported alongside, never as the decision.** It assumes roughly
normal data, and its mean and standard deviation are *not* robust: a handful of
extreme values inflates the standard deviation and hides the very points being
looked for. It is included because it is the method most people expect, and
showing both counts makes the difference visible.

**Skew correction.** Tukey's fences assume a roughly symmetric distribution.
Applied directly to a right-skewed column — transaction amounts, durations,
almost anything money-shaped — they flag several percent of perfectly ordinary
values, because the upper fence sits inside a long, legitimate tail. For a
strongly skewed (`skew > 1`), non-negative column, the fences are therefore
computed on `log1p(x)` and mapped back with `expm1`. The finding records
`"scale": "log1p"` when this happened.

This is the difference between a detector people trust and one they learn to
ignore. On the `clean_transactions.csv` fixture, raw fences flag ~5% of the
log-normal `amount` column; log-scale fences flag none. On `outliers.csv`, the
log-scale fences find **exactly** the 15 injected extremes.

**Guard rails:**

- Fewer than 20 rows: the detector does not run. On a dozen rows, "outside the
  fences" is noise, and a confident-looking finding derived from it would be
  worse than silence.
- Zero IQR (half the values identical): skipped — the fences collapse and would
  flag everything else.
- Below 0.5% of rows: not reported. Some points sit outside the fences in any
  real distribution.
- Above 25% of rows: not reported. At that point the "outliers" *are* the
  distribution — a heavy tail, not a defect.

**An outlier is not an error.** It is a value far from the rest of its column,
which may be entirely legitimate. The finding says exactly that, and recommends
robust statistics rather than deletion.

---

## 4. Anomaly detection (Isolation Forest)

### Why this algorithm

Isolation Forest builds random trees that split on a randomly chosen feature at
a randomly chosen threshold. Points that are easy to separate - those ending up
in short branches - are unusual. It needs no labels, no distance metric and no
assumption of normality, and it scales linearly.

For "find rows that look odd across several numeric columns" it is the right
amount of machine learning: enough to see combinations no per-column rule can,
not so much that the result stops being explainable.

### Feature preparation

| Step | Decision |
| --- | --- |
| Select | Numeric columns, including text columns that hold numbers. Excludes constants (no signal) and integer surrogate keys (a row is not anomalous for having a high id). |
| Drop | Features more than 50% missing. Filling in most of a column invents the very structure the model then "finds". |
| Impute | Remaining gaps with the column **median**, not the mean - the mean is dragged by the outliers being looked for, which would pull imputed rows towards them. |
| Scale | **Not applied.** See below. |

**On scaling.** Obseil deliberately does *not* standardise before fitting.
Isolation Forest splits one feature at a time at a threshold drawn uniformly
from that feature's observed range, so it is invariant to per-feature affine
rescaling: standardising would add a step that changes nothing while implying
it matters. This is *not* true of distance-based detectors - a Local Outlier
Factor or DBSCAN detector added later **must** scale, and
`app.ml.features.scale_features` exists for exactly that.

### Refusals

Detection is **skipped**, with the reason recorded and shown, when:

- fewer than **2 usable numeric features** - one feature can only rediscover
  what the IQR rule already reports, so running it would produce duplicate
  findings dressed up as machine learning;
- fewer than **50 rows** - the forest has too little to isolate against, and
  "unusual" stops meaning anything.

A skip is a normal outcome, not a failure. Saying so is more useful than
returning a confident-looking empty result.

### Where the threshold comes from

This is the part that matters most in practice, and the part most
implementations get wrong.

scikit-learn's `contamination="auto"` sets a fixed score offset taken from the
original paper. On data with no strong anomaly structure the scores cluster
tightly around that offset and it labels **roughly half the dataset**
anomalous. Measured on Obseil's own clean fixture: **49% flagged**. That is
worse than useless - it destroys trust in every other number on the page.

So the forest is used for what it is genuinely good at - **ranking** rows by how
easily they isolate - and the threshold is derived from the resulting score
distribution using the **Iglewicz-Hoaglin modified z-score**: flag scores more
than 3.5 MAD-based deviations above the median. (When more than half the scores
are identical the MAD is zero, and their published mean-absolute-deviation
fallback applies.) Median and MAD are used rather than mean and standard
deviation for the same reason as everywhere else in Obseil: the non-robust
versions are dragged by the very points being looked for.

Two guard rails follow:

- the flagged set never exceeds **2% of rows** - anomalies are rare by
  definition, and a list of 300 is a list nobody reads;
- an operator who genuinely knows their expected rate can set
  `OBSEIL_ANOMALY_CONTAMINATION` to a float, and scikit-learn's own
  thresholding is used instead.

**No threshold here is objectively correct.** Unsupervised anomaly detection has
no ground truth to calibrate against; every cut-off trades false positives
against misses. What Obseil commits to is that the rule is standard, stated and
reproducible - and that a handful of candidates on an otherwise clean dataset is
an expected outcome, not a bug. The finding says so.

### What is reported, and what is not

For each anomalous row Obseil stores the model score (rescaled 0-100 *within
that dataset*), the feature values the model actually saw, and which of those
values sit furthest from their column's median in IQR units.

That last item is **descriptive, not causal**. Isolation Forest exposes no
per-feature attribution, and inventing one would misrepresent the model. The API
and the UI both say, in as many words: *the model reports that a row is unusual;
it does not know why.*

The 0-100 score is likewise **not a probability** and is **not comparable across
datasets** - it is a min-max rescaling of the raw scores within one run.

### Measured result

On `anomalous_transactions.csv`, whose twelve injected rows are ordinary in
every individual column (the entire rule engine reports **zero** findings on
it), the model ranks all twelve inside its top fourteen and flags **12 of 12**.

That test lives in `backend/tests/unit/ml/test_isolation_forest.py` and is the
load-bearing assertion for the whole ML component: if it fails, the machine
learning is decoration.

---

## 5. Quality score

One 0-100 number that you can argue with.

The score is **not** a model output and not a magic constant. It is a
transparent penalty sum:

```
score = 100 - sum over dimensions of min(dimension penalty, dimension cap)

finding penalty = severity weight x coverage multiplier
```

### Severity weights

| Severity | Weight |
| --- | --- |
| Critical | 30 |
| High | 18 |
| Medium | 8 |
| Low | 2 |

### Coverage multiplier

`0.5 + (affected share)`, spanning **0.5x to 1.5x**.

Severity dominates; coverage modulates. A critical finding affecting 5% of rows
should outrank a low finding affecting all of them - the multiplier is wide
enough to distinguish "one bad row" from "the whole column", and deliberately
not wide enough to let a trivial issue outweigh a serious one.

### Dimension caps

| Dimension | Cap | Covers |
| --- | --- | --- |
| Completeness | 35 | Missing values, empty columns, incomplete rows |
| Uniqueness | 25 | Duplicate rows, duplicate identifiers |
| Validity | 25 | Negative values, invalid dates, empty strings |
| Consistency | 10 | Constant columns, high cardinality, numbers as text, padding |
| Distribution | 15 | Statistical outliers |
| Anomalies | 10 | ML-detected unusual rows |

A file with forty partially-empty columns is bad, but it is not forty times
worse than one with four; without a ceiling the score would saturate at zero and
stop discriminating between bad and awful.

The caps **sum to 120, not 100**, on purpose: a dataset genuinely broken in
every dimension can reach zero. If they summed to 100, nothing ever could.

ML anomalies carry the smallest cap because they are candidates for review, not
established defects. The score should not punish a dataset for having rows a
model found interesting.

### Grades

| Score | Grade |
| --- | --- |
| 95-100 | Excellent |
| 80-94 | Good |
| 60-79 | Needs attention |
| 40-59 | Poor |
| 0-39 | Critical |

### The derivation is always returned

Every term - each dimension's raw penalty, its cap, whether it was capped, and
the individual findings ranked by cost - is stored with the analysis and served
by `GET /datasets/{id}/score`. The UI can therefore always answer "why this
score?", and a user who disagrees can point at the specific line they disagree
with.

### Measured result on the sample datasets

| Dataset | Score | Grade |
| --- | --- | --- |
| `clean_transactions.csv` | ~96 | Excellent |
| `anomalous_transactions.csv` | ~96 | Excellent - structurally sound, some rows worth a look |
| `outliers.csv` | ~82 | Good |
| `duplicate_records.csv` | ~72 | Needs attention |
| `missing_values.csv` | ~64 | Needs attention |
| `invalid_values.csv` | ~61 | Needs attention |

The anomaly fixture scoring as highly as the clean one is the rule/ML
distinction showing up in the score itself: nothing about that dataset is
*wrong*, twelve rows are merely worth looking at.

---

## 6. Extending this

Every threshold in this document is a named constant in the module that uses it,
with the reasoning in a comment beside it. If you change one, the fixture tests
in `backend/tests/unit/quality/test_engine.py` will tell you what it cost.

To add a detector, see [CONTRIBUTING.md](../CONTRIBUTING.md). The bar for a new
one is:

1. It is **deterministic** and reproducible.
2. It **explains itself** — all five questions answered.
3. It stays **silent on `clean_transactions.csv`**.
4. It is justified from the data, not from an assumption about what the data
   means.
