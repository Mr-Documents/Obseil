#!/usr/bin/env python3
"""Generate the Obseil sample datasets.

Each file targets one specific behaviour of the analysis pipeline, so that a
test can assert "this detector fires here and stays quiet there". The generator
is committed alongside the data: the seed is fixed, so anyone can regenerate
byte-identical files and see exactly how each defect was introduced.

    python data/generate_samples.py

See ``data/samples/README.md`` for what each file is designed to exercise.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260831
OUTPUT_DIR = Path(__file__).resolve().parent / "samples"

MERCHANT_CATEGORIES = [
    "groceries",
    "fuel",
    "restaurants",
    "utilities",
    "travel",
    "electronics",
    "healthcare",
]
CHANNELS = ["online", "in_store", "mobile"]
COUNTRIES = ["GB", "US", "DE", "FR", "NL", "ES"]


def _base_transactions(rng: np.random.Generator, rows: int) -> pd.DataFrame:
    """A plausible card-transaction table with no injected defects.

    Amounts are log-normal because real spend is: many small purchases, a long
    right tail. Using a normal distribution here would make the outlier and
    anomaly fixtures unrealistically easy.
    """
    start = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {
            "transaction_id": [f"TXN-{index:06d}" for index in range(1, rows + 1)],
            "customer_id": [f"CUST-{value:04d}" for value in rng.integers(1, 400, rows)],
            "transaction_date": [
                (start + pd.Timedelta(int(offset), unit="D")).strftime("%Y-%m-%d")
                for offset in rng.integers(0, 180, rows)
            ],
            "amount": np.round(rng.lognormal(mean=3.1, sigma=0.75, size=rows), 2),
            "items": rng.integers(1, 12, rows),
            "merchant_category": rng.choice(MERCHANT_CATEGORIES, rows),
            "channel": rng.choice(CHANNELS, rows, p=[0.45, 0.35, 0.20]),
            "country": rng.choice(COUNTRIES, rows, p=[0.4, 0.2, 0.12, 0.12, 0.08, 0.08]),
            "customer_age": rng.integers(18, 82, rows),
            "loyalty_points": rng.integers(0, 5000, rows),
        }
    )


def clean_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """No missing values, no duplicates, no constants, no extreme outliers.

    The baseline: Obseil should score this highly and raise few or no findings.
    """
    frame = _base_transactions(rng, 600)
    # Clip the log-normal tail so the IQR rule has nothing legitimate to flag.
    upper = frame["amount"].quantile(0.99)
    frame["amount"] = frame["amount"].clip(upper=round(float(upper), 2))
    return frame


def missing_values_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """Four grades of missingness, so severity banding can be tested.

    * ``country``          ~4%   -> low
    * ``customer_age``     ~18%  -> medium
    * ``loyalty_points``   ~45%  -> high
    * ``promo_code``       ~92%  -> critical
    Plus 12 rows that are mostly empty, for the row-level missingness check.
    """
    frame = _base_transactions(rng, 500)
    frame["promo_code"] = rng.choice(["SPRING10", "WELCOME", "VIP"], len(frame))

    for column, rate in (
        ("country", 0.04),
        ("customer_age", 0.18),
        ("loyalty_points", 0.45),
        ("promo_code", 0.92),
    ):
        mask = rng.random(len(frame)) < rate
        frame.loc[mask, column] = np.nan

    sparse_rows = rng.choice(frame.index, size=12, replace=False)
    sparse_columns = [
        "customer_id",
        "transaction_date",
        "amount",
        "items",
        "merchant_category",
        "channel",
        "country",
        "customer_age",
    ]
    frame.loc[sparse_rows, sparse_columns] = np.nan
    return frame


def duplicate_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """40 exactly duplicated rows plus 25 reused transaction ids.

    The two defects are distinct: a fully duplicated row is double counting,
    while a repeated id in an otherwise-unique column is a broken key.
    """
    frame = _base_transactions(rng, 400)

    # Break the key first, then duplicate rows. Doing it the other way round
    # would overwrite some of the duplicated rows and silently reduce the count.
    collision_rows = rng.choice(frame.index, size=25, replace=False)
    frame.loc[collision_rows, "transaction_id"] = "TXN-000001"

    untouched = frame.index.difference(collision_rows)
    repeated = frame.loc[rng.choice(untouched, size=40, replace=False)]
    frame = pd.concat([frame, repeated], ignore_index=True)

    return frame.sample(frac=1, random_state=11).reset_index(drop=True)


def outlier_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """Univariate outliers that a single-column rule should catch.

    ``amount`` gets 15 values three orders of magnitude above the body of the
    distribution; ``customer_age`` gets 8 impossible values. Both are visible
    without looking at any other column, which is what separates them from the
    anomaly fixture below.
    """
    frame = _base_transactions(rng, 500)

    extreme_rows = rng.choice(frame.index, size=15, replace=False)
    frame.loc[extreme_rows, "amount"] = np.round(rng.uniform(45_000, 120_000, 15), 2)

    impossible_ages = rng.choice(frame.index.difference(extreme_rows), size=8, replace=False)
    frame.loc[impossible_ages, "customer_age"] = rng.choice([0, 1, 199, 240], 8)

    return frame


def invalid_values_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """Values that are the wrong *kind* of thing, not merely unusual.

    * negative ``amount`` and ``items`` where only positives are possible
    * unparseable and impossible ``transaction_date`` values
    * empty and whitespace-only strings that are not detected as missing
    * a column that is numeric except for a handful of text values
    * a constant column, which carries no information at all
    """
    frame = _base_transactions(rng, 450)
    frame["batch_version"] = "v3"  # constant column

    negative_amounts = rng.choice(frame.index, size=18, replace=False)
    frame.loc[negative_amounts, "amount"] = -frame.loc[negative_amounts, "amount"]

    negative_items = rng.choice(frame.index.difference(negative_amounts), size=9, replace=False)
    frame.loc[negative_items, "items"] = -1

    frame["transaction_date"] = frame["transaction_date"].astype(object)
    bad_dates = rng.choice(frame.index, size=14, replace=False)
    frame.loc[bad_dates, "transaction_date"] = np.resize(
        ["not-a-date", "2026-13-45", "31/02/2026", ""], 14
    )

    frame["merchant_category"] = frame["merchant_category"].astype(object)
    blank_categories = rng.choice(frame.index, size=11, replace=False)
    frame.loc[blank_categories, "merchant_category"] = np.resize(["", "   ", "  "], 11)

    frame["loyalty_points"] = frame["loyalty_points"].astype(object)
    text_in_numeric = rng.choice(frame.index, size=6, replace=False)
    frame.loc[text_in_numeric, "loyalty_points"] = np.resize(["unknown", "n/a "], 6)

    return frame


def anomaly_dataset(rng: np.random.Generator) -> pd.DataFrame:
    """Multivariate anomalies: no single column looks wrong.

    The trick is that the normal data has *structure* — amount is driven by the
    basket size, and loyalty points accumulate with customer age. Twelve rows
    then violate that structure while keeping every individual value inside its
    own column's ordinary range:

    * a basket of one item priced like a basket of ten
    * an 18-year-old with a maximal loyalty balance

    Every marginal distribution is untouched, so no per-column rule can fire.
    What is unusual is the *combination*, which places these rows in a sparsely
    populated region of the joint distribution — exactly what an Isolation
    Forest is for, and exactly what an interquartile-range check cannot see.
    """
    frame = _base_transactions(rng, 700)

    # Give the data real structure for the anomalies to violate.
    unit_price = rng.lognormal(mean=2.0, sigma=0.45, size=len(frame))
    frame["amount"] = np.round(frame["items"] * unit_price + rng.normal(0, 1.5, len(frame)), 2)
    # Clip the tail so the per-column outlier rule has nothing legitimate to
    # flag: this fixture must isolate the *multivariate* case and nothing else.
    frame["amount"] = frame["amount"].clip(
        lower=1.0, upper=round(float(frame["amount"].quantile(0.97)), 2)
    )
    frame["loyalty_points"] = np.round(
        (frame["customer_age"] - 18) * 60 + rng.normal(0, 250, len(frame))
    ).clip(0, 5000).astype(int)

    anomalous_rows = rng.choice(frame.index, size=12, replace=False)

    # A single item priced like a full basket: the amount stays inside the
    # column's normal range, but not for one item.
    frame.loc[anomalous_rows, "items"] = 1
    frame.loc[anomalous_rows, "amount"] = np.round(
        rng.uniform(
            float(frame["amount"].quantile(0.85)), float(frame["amount"].quantile(0.99)), 12
        ),
        2,
    )

    # A very young customer with a very long-standing loyalty balance.
    frame.loc[anomalous_rows, "customer_age"] = rng.integers(18, 21, 12)
    frame.loc[anomalous_rows, "loyalty_points"] = rng.integers(4200, 4900, 12)

    return frame


GENERATORS = {
    "clean_transactions": clean_dataset,
    "missing_values": missing_values_dataset,
    "duplicate_records": duplicate_dataset,
    "outliers": outlier_dataset,
    "invalid_values": invalid_values_dataset,
    "anomalous_transactions": anomaly_dataset,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    for name, generator in GENERATORS.items():
        # A fresh generator per dataset keeps each file stable even if another
        # generator is later added, removed or reordered.
        frame = generator(np.random.default_rng(SEED))
        destination = args.output / f"{name}.csv"
        frame.to_csv(destination, index=False)
        print(f"{destination.name:<32} {len(frame):>6} rows x {frame.shape[1]} columns")

    # One XLSX so the Excel reader has a fixture too.
    excel_path = args.output / "clean_transactions.xlsx"
    clean_dataset(np.random.default_rng(SEED)).to_excel(
        excel_path, index=False, sheet_name="transactions"
    )
    print(f"{excel_path.name:<32} (Excel workbook)")


if __name__ == "__main__":
    main()
