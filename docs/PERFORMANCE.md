# Obseil performance

Measured, not assumed. Every number here came from
`backend/scripts/benchmark_pipeline.py`, which anyone can re-run.

```bash
cd backend
python scripts/benchmark_pipeline.py
```

---

## Where the time goes

The analysis pipeline is four stages over a `pandas.DataFrame`:

```
profile  →  quality detectors  →  anomaly detection  →  score
```

Measured on a warm process (Windows laptop, Python 3.13), synthetic data with
half numeric and half categorical columns. Rows above the sampling default are
shown for context — in practice they are analysed as a 50,000-row sample.

| Rows | Columns | Profile | Quality | Anomaly | Total | Peak |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 10 | 0.04 s | 0.01 s | 0.20 s | **0.25 s** | 1 MB |
| 10,000 | 10 | 0.20 s | 0.02 s | 0.40 s | **0.62 s** | 4 MB |
| 50,000 | 20 | 0.85 s | 0.15 s | 1.31 s | **2.30 s** | 14 MB |
| 50,000 | 60 | 2.18 s | 0.35 s | 1.30 s | **3.83 s** | 35 MB |
| 200,000 | 20 | 2.83 s | 0.71 s | 4.96 s | **8.50 s** | 67 MB |
| 200,000 | 60 | 7.76 s | 1.64 s | 5.21 s | **14.61 s** | 166 MB |

**Profiling dominates below ~50,000 rows and scales with *columns***: each
column costs a distinct-value count, a value-count, and — for text columns — a
pass for length and whitespace statistics. Above that, anomaly scoring takes
over, because `score_samples` walks every row through 200 trees.

### A measurement trap worth naming

The first version of this benchmark timed each stage **with `tracemalloc`
running**, and reported the 50,000 × 60 case at 14.6 s rather than 3.8 s. The
allocation profiler roughly triples the cost of allocation-heavy pandas code.

Timing and memory are now measured in separate passes, with a warm-up pass
first. It is worth stating because the wrong numbers would have justified the
wrong decisions — the sampling threshold below was very nearly set from them.

---

## Two inefficiencies found and fixed

Both were found by running the benchmark, not by reading the code.

### Deep memory accounting was computed twice

`profile_dataset` called `frame.memory_usage(deep=True)` for the dataset total,
and `profile_column` called `series.memory_usage(deep=True)` again for each
column. `deep=True` walks every object in a column, so this doubled the most
expensive single operation in profiling for text-heavy data.

The frame-level call now happens once and the per-column figures are passed
down. Measured with the same harness before and after, profiling a
200,000 × 60 dataset went from **41.2 s to 26.8 s — a 35% reduction**. (Both
figures are from the instrumented pass, so they are comparable with each other
but higher than the clean timings in the table above.)

### Robust deviations were computed for every row

The Isolation Forest reports which of an anomalous row's values sit furthest
from their column's centre. That was computed for the whole frame, then read
for the ~2% of rows actually flagged.

`robust_deviations` now takes a `subset`, centring and scaling against the
**whole** column — so the numbers are identical — while materialising only the
rows anyone will look at.

---

## The sampling threshold

Analysis runs **inline in the upload request**. There is no queue and no
worker, because a background job system is an operational dependency the MVP
does not need — the split between "store the file" and "analyse it" already
exists in the service layer, so introducing one later is a change of caller,
not of design.

That decision has a consequence: the analysis must finish in seconds.

Two ceilings apply, both configurable:

| Setting | Default | Behaviour |
| --- | --- | --- |
| `OBSEIL_PROFILE_SAMPLE_ROWS` | 50,000 | Above this, the analysis runs on a deterministic head sample |
| `OBSEIL_MAX_ANALYSIS_ROWS` | 1,000,000 | Above this, the dataset is refused outright |

**The sample threshold was 200,000 and was lowered to 50,000 on the evidence
above.** A 200,000 × 60 file takes ~14.6 s to analyse even after the fixes;
50,000 rows takes ~3.8 s. Fifty thousand rows is far more than any of the
quality statistics need to be reliable, and it keeps the worst accepted case
under **four seconds**.

Sampling is never silent. The profile records `sampled`, `sampled_rows` and
`source_rows`; the API returns all three; the dashboard says *"Sampled from
200,000 rows"* on the row tile and adds a note explaining how the file was
read. No percentage is ever computed against the wrong denominator.

**Above one million rows the dataset is refused**, because a partial answer
presented as a whole-file answer is worse than no answer.

---

## Memory

Peak allocation is in the table above, tracked with `tracemalloc` in its own
pass. At the 50,000-row sampling default an analysis peaks at ~35 MB over and
above the frame itself, so it stays comfortably inside a small container.

The file is read **once** and the same frame is handed to every stage —
re-reading a 50 MB CSV four times would dominate the runtime.

---

## Database

Query patterns were chosen to keep listing costs flat:

- **Project list roll-ups** are three queries regardless of how many projects
  or datasets exist — two grouped aggregates and one page query — rather than
  loading each project's relationships.
- **History version numbers** are computed with one grouped query, not one per
  row. A project with two hundred analyses costs the same as one with two.
- **Finding severity counts** are denormalised onto the analysis row, so the
  dashboard and the history list never aggregate the findings table.
- **Indexes** cover every listing and filter path: `(owner_id, updated_at)` on
  projects, `(project_id, created_at)` on datasets and analyses,
  `(analysis_id, severity)` and `(dataset_id, status)` on findings, and
  `(analysis_id, rank)` on anomalies.

Findings are sorted by an integer `severity_rank` column, not by the severity
string — ordering by the text would give `critical < high < low < medium`.

---

## Frontend

Production build, gzipped:

| Chunk | Raw | Gzipped |
| --- | ---: | ---: |
| `vendor` (React, Router) | 165 kB | 54 kB |
| `index` (application) | 226 kB | 63 kB |
| `charts` (Recharts + d3) | 394 kB | 108 kB |

Recharts is split into its own chunk so the authentication and project screens
do not pay for it. Fonts are self-hosted and subset by `@fontsource`, so there
is no third-party request on first paint.

Data-heavy views are paginated server-side with a server-enforced cap: the row
explorer requests at most 200 rows per page, findings 200, anomalies 200. The
whole file is never sent to the browser.

---

## What would need to change at a larger scale

Deliberately not built now, but nothing here requires a rewrite:

| Pressure | Response |
| --- | --- |
| Analyses slower than a request should be | Move `analyze_dataset` behind a queue; the upload/analyse split already exists |
| Files larger than 50 MB | Chunked upload to S3-compatible storage; `StorageBackend` is already an interface |
| Very wide datasets (500+ columns) | Profile columns in a process pool — each column profile is independent |
| Many concurrent analyses | Horizontal scale; the API holds no per-analysis state between requests |
