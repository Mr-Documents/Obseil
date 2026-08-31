"""Shared test data helpers.

The committed sample datasets are the fixtures of record — see
``data/samples/README.md``. This module locates them and provides small
in-memory frames for tests that want to isolate one condition exactly.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


def sample_path(name: str) -> Path:
    """Absolute path to a committed sample dataset."""
    path = SAMPLES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"Sample dataset {name!r} is missing. Run `python data/generate_samples.py`."
        )
    return path


def sample_bytes(name: str) -> bytes:
    return sample_path(name).read_bytes()


def load_sample(name: str) -> pd.DataFrame:
    return pd.read_csv(sample_path(name))


# --- Minimal hand-built frames ---------------------------------------------
def clean_frame(rows: int = 100) -> pd.DataFrame:
    """A tiny well-behaved frame with one column of each inferred type."""
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "id": range(1, rows + 1),
            "amount": np.round(rng.normal(100, 15, rows), 2),
            "category": rng.choice(["a", "b", "c"], rows),
            "active": rng.choice([True, False], rows),
            "created_at": pd.date_range("2026-01-01", periods=rows, freq="D"),
        }
    )


def frame_with_missing(rows: int = 100, missing: int = 30) -> pd.DataFrame:
    frame = clean_frame(rows)
    frame.loc[: missing - 1, "amount"] = np.nan
    return frame
