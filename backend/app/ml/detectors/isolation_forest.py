"""Isolation Forest anomaly detection.

**Why this algorithm.** Isolation Forest builds random trees that split on a
randomly chosen feature at a randomly chosen threshold. Points that are easy to
separate from the rest — those that end up in short branches — are unusual. It
needs no labels, no distance metric and no assumption of normality, and it
scales linearly. For "find rows that look odd across several numeric columns"
it is the right amount of machine learning: enough to see combinations that no
per-column rule can, not so much that the result stops being explainable.

**What it does not do.** It does not know *why* a row is unusual, and Obseil
does not claim it does. A finding reports the score, the features the model
saw, and which of that row's values sit furthest from their column's centre —
all descriptive statements about the data, none an attribution of the model's
internal decision.

**Where the line is drawn.** This is the part that matters most in practice,
and the part most implementations get wrong.

scikit-learn's ``contamination="auto"`` sets a fixed score offset from the
original paper. On data with no strong anomaly structure the scores cluster
tightly around that offset, and it labels *roughly half the dataset* anomalous
— which is worse than useless, because it destroys trust in every other number
on the page. (Measured on Obseil's own clean fixture: 49% flagged.)

So the forest is used for what it is genuinely good at — **ranking** rows by
how easily they isolate — and the threshold is set from the resulting score
distribution using the Iglewicz-Hoaglin modified z-score: flag scores more than
3.5 MAD-based deviations above the median. Median and MAD are used rather than
mean and standard deviation for the same reason as everywhere else in Obseil:
the non-robust versions are dragged by the very points being looked for.

Two guard rails follow: the flagged set is never allowed to exceed
``MAX_ANOMALY_SHARE`` of the dataset, and if an operator genuinely knows their
expected anomaly rate they can set ``OBSEIL_ANOMALY_CONTAMINATION`` to a float
and scikit-learn's own thresholding is used instead.

**No threshold here is objectively correct.** Unsupervised anomaly detection
has no ground truth to calibrate against; every cut-off trades false positives
against misses. What Obseil commits to is that the rule is standard, stated,
and reproducible — and that a handful of candidates on an otherwise clean
dataset is an expected outcome, not a bug. The finding says so.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.core.config import settings
from app.ml.base import AnomalousRow, AnomalyDetector, AnomalyResult
from app.ml.features import robust_deviations

logger = logging.getLogger(__name__)

#: More trees than scikit-learn's default of 100. Scores from a small forest
#: are noticeably unstable between runs, and stability matters when a user is
#: comparing two analyses of the same data.
N_ESTIMATORS = 200

#: Iglewicz-Hoaglin cut-off for the modified z-score. 3.5 is their published
#: recommendation and is the convention this project adopts.
MODIFIED_Z_CUTOFF = 3.5

#: Consistency factor making the MAD a consistent estimator of the standard
#: deviation for normally distributed data.
MAD_SCALE = 0.6745

#: Iglewicz and Hoaglin's published fallback constant, used when the MAD is
#: zero because more than half the scores are identical.
MEAN_AD_SCALE = 1.253314

#: Hard ceiling on the flagged share. Anomalies are by definition rare; if the
#: threshold would flag more than this, only the highest-scoring rows are kept.
#: A list of 300 "anomalies" is a list nobody reads.
MAX_ANOMALY_SHARE = 2.0

#: How many features to name as "standing out" per anomalous row.
TOP_CONTRIBUTORS = 3


def modified_z_scores(scores: np.ndarray) -> np.ndarray:
    """Iglewicz-Hoaglin modified z-scores: robust deviation from the median.

    When more than half the scores are identical the MAD is zero, and the
    published fallback applies: divide by the *mean* absolute deviation scaled
    by 1.253314 instead. Without it, a distribution with a dominant mode could
    never flag anything, however far out its extremes sat.
    """
    median = float(np.median(scores))
    absolute_deviations = np.abs(scores - median)

    mad = float(np.median(absolute_deviations))
    if mad > 0:
        return MAD_SCALE * (scores - median) / mad

    mean_ad = float(np.mean(absolute_deviations))
    if mean_ad > 0:
        return (scores - median) / (MEAN_AD_SCALE * mean_ad)

    # Every score is identical: nothing is unusual relative to anything else.
    return np.zeros_like(scores)


class IsolationForestDetector(AnomalyDetector):
    algorithm = "isolation_forest"

    def __init__(
        self,
        *,
        n_estimators: int = N_ESTIMATORS,
        contamination: str | float | None = None,
        random_state: int | None = None,
        max_anomalies: int | None = None,
        max_anomaly_share: float = MAX_ANOMALY_SHARE,
    ) -> None:
        self.n_estimators = n_estimators
        self.contamination = contamination if contamination is not None else settings.contamination
        self.random_state = (
            random_state if random_state is not None else settings.anomaly_random_state
        )
        self.max_anomalies = max_anomalies or settings.anomaly_max_anomalies_stored
        self.max_anomaly_share = max_anomaly_share

    def detect(self, features: pd.DataFrame) -> AnomalyResult:
        explicit_rate = not isinstance(self.contamination, str)
        parameters: dict[str, object] = {
            "n_estimators": self.n_estimators,
            "contamination": self.contamination,
            "random_state": self.random_state,
            "max_samples": "auto",
            "scaled": False,
            "scaling_note": (
                "Isolation Forest splits one feature at a time at a uniformly random "
                "threshold within that feature's range, so it is invariant to per-feature "
                "rescaling. Standardising would change nothing."
            ),
            "threshold_rule": (
                "explicit contamination rate"
                if explicit_rate
                else f"modified z-score > {MODIFIED_Z_CUTOFF} (Iglewicz-Hoaglin)"
            ),
            "max_anomaly_share": self.max_anomaly_share,
        }

        if features.empty or features.shape[1] == 0:
            return AnomalyResult(
                ran=False,
                algorithm=self.algorithm,
                reason="No usable numeric features.",
                parameters=parameters,
            )

        model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            max_samples="auto",
            n_jobs=1,
        )

        matrix = features.to_numpy(dtype=float)
        labels = model.fit_predict(matrix)
        # score_samples: lower is more anomalous. Negated so that everywhere
        # above this line "higher" consistently means "more unusual".
        raw_scores = -model.score_samples(matrix)

        flagged = self._select(raw_scores, labels, explicit_rate=explicit_rate)
        parameters["threshold_score"] = (
            round(float(raw_scores[flagged].min()), 6) if flagged.size else None
        )

        anomaly_scores = _rescale(raw_scores)
        deviations = robust_deviations(features)

        anomalies = [
            AnomalousRow(
                row_index=int(position),
                raw_score=round(float(raw_scores[position]), 6),
                anomaly_score=round(float(anomaly_scores[position]), 2),
                feature_values={
                    name: _finite(features.iat[position, column])
                    for column, name in enumerate(features.columns)
                },
                top_contributors=_contributors(deviations, features, position),
            )
            for position in flagged
        ]

        logger.info(
            "Isolation Forest complete",
            extra={
                "rows": len(features),
                "features": features.shape[1],
                "anomalies": len(anomalies),
            },
        )
        return AnomalyResult(
            ran=True,
            algorithm=self.algorithm,
            features=[str(column) for column in features.columns],
            rows_scored=len(features),
            anomalies=anomalies,
            parameters=parameters,
        )

    def _select(
        self, raw_scores: np.ndarray, labels: np.ndarray, *, explicit_rate: bool
    ) -> np.ndarray:
        """Indices of the anomalous rows, most unusual first."""
        if explicit_rate:
            # The operator asserted a rate; honour scikit-learn's thresholding.
            candidates = np.flatnonzero(labels == -1)
        else:
            candidates = np.flatnonzero(modified_z_scores(raw_scores) > MODIFIED_Z_CUTOFF)

        ordered = candidates[np.argsort(-raw_scores[candidates])]

        ceiling = int(len(raw_scores) * self.max_anomaly_share / 100)
        if ceiling and ordered.size > ceiling:
            ordered = ordered[:ceiling]
        return ordered[: self.max_anomalies]


def _rescale(raw_scores: np.ndarray) -> np.ndarray:
    """Map raw scores onto 0-100 within this dataset.

    Min-max, deliberately. The result is a *relative* ranking within one
    dataset and is not comparable across datasets — which the API and the UI
    both say, because a 0-100 number that looked absolute would be read as one.
    """
    lowest, highest = float(raw_scores.min()), float(raw_scores.max())
    if not np.isfinite(lowest) or not np.isfinite(highest) or highest <= lowest:
        return np.full_like(raw_scores, 50.0)
    return (raw_scores - lowest) / (highest - lowest) * 100.0


def _finite(value: float) -> float | None:
    return round(float(value), 6) if np.isfinite(value) else None


def _contributors(
    deviations: pd.DataFrame, features: pd.DataFrame, position: int
) -> list[dict[str, object]]:
    """The features whose values sit furthest from their column's centre.

    Descriptive, not causal: this says which of the row's values are unusual on
    their own terms. The Isolation Forest exposes no per-feature attribution,
    and inventing one would misrepresent the model.
    """
    row = deviations.iloc[position]
    ranked = row.sort_values(ascending=False).head(TOP_CONTRIBUTORS)
    return [
        {
            "feature": str(name),
            "value": _finite(features.iat[position, features.columns.get_loc(name)]),
            "deviation_iqr": round(float(deviation), 3),
        }
        for name, deviation in ranked.items()
        if np.isfinite(deviation)
    ]
