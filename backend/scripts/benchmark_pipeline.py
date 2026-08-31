#!/usr/bin/env python3
"""Measure the analysis pipeline at several dataset sizes.

The numbers in ``docs/PERFORMANCE.md`` come from this script. Re-run it after
touching the profiling, quality or ML stages - it is how both of the
inefficiencies documented there were found.

    cd backend
    python scripts/benchmark_pipeline.py

Timing and memory are measured in **separate passes**: `tracemalloc` roughly
triples the cost of allocation-heavy pandas code, so timing under it reports
the profiler as several times slower than it is. A warm-up pass runs first,
because a running server pays interpreter and scikit-learn start-up once, not
per request.
"""

from __future__ import annotations

import logging
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

# Runnable from the backend directory without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.disable(logging.CRITICAL)

from app.ml import anomaly_finding, detect_anomalies  # noqa: E402
from app.profiling import profile_dataset  # noqa: E402
from app.quality import run_detectors  # noqa: E402
from app.quality.scoring import calculate_quality_score  # noqa: E402

#: (rows, columns) pairs spanning "typical" to "the hard ceiling".
SIZES: tuple[tuple[int, int], ...] = (
    (1_000, 10),
    (10_000, 10),
    (50_000, 20),
    (50_000, 60),
    (200_000, 20),
    (200_000, 60),
)


def make_frame(rows: int, columns: int, seed: int = 0) -> pd.DataFrame:
    """A dataset shaped like the ones Obseil actually sees.

    Half numeric with a realistic right skew, the rest categorical, plus an
    identifier and a timestamp - the mix that determines which code paths in
    the profiler get exercised.
    """
    rng = np.random.default_rng(seed)
    numeric = max(columns // 2, 2)

    data: dict[str, object] = {}
    for index in range(numeric):
        data[f"metric_{index}"] = np.round(rng.lognormal(3, 0.8, rows), 2)
    for index in range(max(columns - numeric - 2, 0)):
        data[f"category_{index}"] = rng.choice(["alpha", "beta", "gamma", "delta"], rows)
    data["record_id"] = [f"REC-{value:08d}" for value in range(rows)]
    data["observed_at"] = pd.date_range("2026-01-01", periods=rows, freq="min").astype(str)
    return pd.DataFrame(data)


def stage_timings(frame: pd.DataFrame) -> dict[str, float]:
    """Time each pipeline stage over an already-loaded frame."""
    timings: dict[str, float] = {}

    started = time.perf_counter()
    profile = profile_dataset(frame)
    timings["profile"] = time.perf_counter() - started

    started = time.perf_counter()
    findings = run_detectors(frame, profile)
    timings["quality"] = time.perf_counter() - started

    started = time.perf_counter()
    result = detect_anomalies(frame, profile)
    timings["anomaly"] = time.perf_counter() - started

    started = time.perf_counter()
    ml_finding = anomaly_finding(result, profile.row_count)
    if ml_finding is not None:
        findings.append(ml_finding)
    calculate_quality_score(findings)
    timings["score"] = time.perf_counter() - started

    timings["findings"] = len(findings)
    timings["anomalies"] = result.anomaly_count
    return timings


def main() -> None:
    # Warm up pandas, numpy and scikit-learn so the first row of the table is
    # not reporting import and first-call costs as pipeline time.
    stage_timings(make_frame(2_000, 8))

    print(
        f"{'rows':>9} {'cols':>5} {'profile':>9} {'quality':>9} {'anomaly':>9} "
        f"{'score':>8} {'total':>8} {'peak MB':>9} {'findings':>9}"
    )
    for rows, columns in SIZES:
        frame = make_frame(rows, columns)

        # Pass one: timing, with no profiler attached.
        timings = stage_timings(frame)

        # Pass two: peak allocation. Its overhead does not pollute the timings.
        tracemalloc.start()
        stage_timings(frame)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        total = timings["profile"] + timings["quality"] + timings["anomaly"] + timings["score"]
        print(
            f"{rows:>9,} {columns:>5} {timings['profile']:>8.2f}s {timings['quality']:>8.2f}s "
            f"{timings['anomaly']:>8.2f}s {timings['score']:>7.2f}s {total:>7.2f}s "
            f"{peak / 1024 / 1024:>8.0f} {int(timings['findings']):>9}"
        )


if __name__ == "__main__":
    main()
