"""Routers: text+metadata, metadata-only, and the Tier-majority reference.

Three routers, all trained offline on already-observed outcomes:

``TextMetadataRouter``
    The main learned router.  TF-IDF over the problem statement, concatenated
    with one-hot source, multi-hot domain, and scaled numeric difficulty
    features; multinomial logistic regression over the five oracle labels.

``MetadataOnlyRouter``
    Same model, text features removed.  Isolates how much of the router's
    behaviour is metadata memorisation rather than reading the problem.

``TierMajorityRouter``
    Not learned.  A train-split metadata-only reference: predict the majority
    oracle label within the problem's difficulty tier, falling back to the
    train-split global majority for unseen tiers.  This is the heuristic the
    learned routers must beat to be interesting.

Split protocol
--------------
Two split conventions appear in the paper and both are provided:

``SplitConfig.primary()``
    Stratified 80/10/10, seed 42.  The primary held-out split (test n=423 on
    the short-paper benchmark).

``SplitConfig.six_setting()``
    Stratified 70/15/15 by oracle label, seed 20260712.  Hyperparameters are
    chosen on dev ONLY, the model is refit on train+dev, and the untouched
    test IDs are scored once.

Every router fits on training rows only and never sees an outcome column:
features go through :mod:`protocol_routing.features`, which raises on contact
with a label column.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from protocol_routing.features import METADATA_ONLY_SPEC, TEXT_METADATA_SPEC, FeatureSpec, Featurizer
from protocol_routing.metrics import macro_f1
from protocol_routing.protocols import PROTOCOL_ORDER, Protocol, canonical_protocol

#: Label order used by every encoder here.  Fixed so that a saved model's class
#: indices always mean the same protocol.
LABEL_ORDER: tuple[str, ...] = tuple(p.value for p in PROTOCOL_ORDER)


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SplitConfig:
    """Deterministic stratified split configuration."""

    train_ratio: float
    dev_ratio: float
    seed: int
    name: str

    @classmethod
    def primary(cls) -> SplitConfig:
        """Primary paper split: stratified 80/10/10, seed 42."""
        return cls(train_ratio=0.8, dev_ratio=0.1, seed=42, name="primary_80_10_10_seed42")

    @classmethod
    def six_setting(cls) -> SplitConfig:
        """Six-setting router split: stratified 70/15/15, seed 20260712."""
        return cls(train_ratio=0.7, dev_ratio=0.15, seed=20260712, name="six_setting_70_15_15_seed20260712")

    @property
    def test_ratio(self) -> float:
        return 1.0 - self.train_ratio - self.dev_ratio


def _split_sizes(n: int, train_ratio: float, dev_ratio: float) -> list[str]:
    n_train = int(math.floor(n * train_ratio))
    n_dev = int(math.floor(n * dev_ratio))
    n_test = n - n_train - n_dev
    if n >= 3:
        if n_train == 0:
            n_train = 1
        if n_dev == 0:
            n_dev = 1
        n_test = n - n_train - n_dev
        if n_test == 0:
            if n_train >= n_dev and n_train > 1:
                n_train -= 1
            elif n_dev > 1:
                n_dev -= 1
            n_test = n - n_train - n_dev
    return ["train"] * n_train + ["dev"] * n_dev + ["test"] * n_test


def make_splits(
    frame: pd.DataFrame,
    *,
    config: SplitConfig | None = None,
    id_column: str = "problem_uid",
    label_column: str = "oracle_label",
) -> pd.Series:
    """Deterministic label-stratified split assignment.

    Determinism does not depend on input row order: within each label the rows
    are sorted by id before a label-specific seeded shuffle.  Re-exporting the
    upstream table in a different order therefore cannot silently move problems
    between train and test.
    """
    cfg = config or SplitConfig.primary()
    if id_column not in frame.columns:
        raise KeyError(f"Missing id column {id_column!r}")
    if label_column not in frame.columns:
        # Derive it rather than making the caller remember to attach it first.
        # Stratification needs the label, and a caller who forgot it would
        # otherwise be tempted to fall back to an unstratified split, quietly
        # changing the design.
        from protocol_routing.oracle import oracle_label_series

        try:
            frame = frame.assign(**{label_column: oracle_label_series(frame)})
        except KeyError as exc:
            raise KeyError(
                f"Missing label column {label_column!r}, and it could not be "
                f"derived from protocol outcome columns ({exc})."
            ) from exc
    if frame[id_column].duplicated().any():
        raise ValueError(f"{id_column!r} must be unique for a reproducible split")

    assignment: dict[object, str] = {}
    for label in sorted(frame[label_column].astype(str).unique()):
        ids = sorted(frame.loc[frame[label_column].astype(str) == label, id_column].tolist(), key=str)
        material = f"{cfg.seed}:{label}".encode()
        stable_seed = int(hashlib.sha256(material).hexdigest()[:16], 16)
        rng = random.Random(stable_seed)
        rng.shuffle(ids)
        for pid, split in zip(ids, _split_sizes(len(ids), cfg.train_ratio, cfg.dev_ratio)):
            assignment[pid] = split
    return frame[id_column].map(assignment)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def encode_labels(labels: Iterable[str]) -> np.ndarray:
    return np.asarray([LABEL_ORDER.index(canonical_protocol(x).value) for x in labels], dtype=int)


def decode_labels(indices: Iterable[int]) -> list[str]:
    return [LABEL_ORDER[int(i)] for i in indices]


@dataclass
class TierMajorityRouter:
    """Train-split metadata-only reference.

    ``fit`` records the majority oracle label per difficulty tier and the
    train-split global majority.  ``predict`` returns the tier's majority, or
    the global majority for a tier unseen in training.  Ties are broken toward
    the CHEAPER protocol (earlier in ``LABEL_ORDER``), which is the
    conservative choice for a cost-aware baseline.
    """

    tier_column: str = "difficulty_tier"
    tier_majority: dict[object, str] = field(default_factory=dict)
    global_majority: str = Protocol.BASELINE.value

    def fit(self, frame: pd.DataFrame, labels: Sequence[str]) -> TierMajorityRouter:
        series = pd.Series([canonical_protocol(x).value for x in labels], index=frame.index)
        self.global_majority = self._majority(series)
        self.tier_majority = {}
        if self.tier_column in frame.columns:
            for tier, group in series.groupby(frame[self.tier_column]):
                self.tier_majority[tier] = self._majority(group)
        return self

    @staticmethod
    def _majority(series: pd.Series) -> str:
        counts = series.value_counts()
        best = max(
            LABEL_ORDER,
            key=lambda label: (int(counts.get(label, 0)), -LABEL_ORDER.index(label)),
        )
        return best

    def predict(self, frame: pd.DataFrame) -> list[str]:
        if self.tier_column not in frame.columns:
            return [self.global_majority] * len(frame)
        return [self.tier_majority.get(t, self.global_majority) for t in frame[self.tier_column]]


@dataclass
class LogisticRouter:
    """Multinomial logistic router over a :class:`~protocol_routing.features.FeatureSpec`."""

    spec: FeatureSpec = field(default_factory=FeatureSpec)
    C: float = 1.0
    class_weight: str | None = "balanced"
    max_iter: int = 2000
    random_state: int = 42
    featurizer: Featurizer | None = field(default=None, init=False, repr=False)
    model: LogisticRegression | None = field(default=None, init=False, repr=False)

    def fit(self, frame: pd.DataFrame, labels: Sequence[str]) -> LogisticRouter:
        self.featurizer = Featurizer(spec=self.spec)
        x = self.featurizer.fit_transform(frame)
        y = encode_labels(labels)
        self.model = LogisticRegression(
            C=self.C,
            class_weight=self.class_weight,
            max_iter=self.max_iter,
            solver="saga",
            random_state=self.random_state,
        )
        self.model.fit(x, y)
        return self

    def predict(self, frame: pd.DataFrame) -> list[str]:
        if self.model is None or self.featurizer is None:
            raise RuntimeError("Router is not fitted.")
        x = self.featurizer.transform(frame)
        # Map sklearn's own class indices back through LABEL_ORDER: a class
        # absent from the training split would otherwise shift every index.
        classes = list(self.model.classes_)
        raw = self.model.predict(x)
        return [LABEL_ORDER[int(classes[classes.index(int(v))])] for v in raw]

    def predict_proba(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.model is None or self.featurizer is None:
            raise RuntimeError("Router is not fitted.")
        proba = self.model.predict_proba(self.featurizer.transform(frame))
        columns = [LABEL_ORDER[int(c)] for c in self.model.classes_]
        return pd.DataFrame(proba, columns=columns, index=frame.index)


def TextMetadataRouter(**kwargs: object) -> LogisticRouter:
    """Main learned router: TF-IDF text + metadata features."""
    return LogisticRouter(spec=TEXT_METADATA_SPEC, **kwargs)  # type: ignore[arg-type]


def MetadataOnlyRouter(**kwargs: object) -> LogisticRouter:
    """Metadata-only ablation of the learned router."""
    return LogisticRouter(spec=METADATA_ONLY_SPEC, **kwargs)  # type: ignore[arg-type]


#: The hyperparameter grid searched on dev.  Matches the released runs.
DEFAULT_CONFIG_GRID: tuple[Mapping[str, object], ...] = tuple(
    {"class_weight": cw, "C": c}
    for cw in (None, "balanced")
    for c in (0.25, 1.0, 4.0)
)


def select_on_dev(
    make_router,
    train_frame: pd.DataFrame,
    train_labels: Sequence[str],
    dev_frame: pd.DataFrame,
    dev_labels: Sequence[str],
    *,
    grid: Sequence[Mapping[str, object]] = DEFAULT_CONFIG_GRID,
) -> tuple[Mapping[str, object], list[dict[str, object]]]:
    """Choose hyperparameters on DEV only; returns ``(best_config, search_log)``.

    Selection metric is dev macro-F1.  The test split is never touched here --
    that is the point of the function existing separately from ``fit``.
    """
    log: list[dict[str, object]] = []
    best: Mapping[str, object] | None = None
    best_score = -1.0
    for config in grid:
        router = make_router(**config)
        router.fit(train_frame, train_labels)
        score = macro_f1(list(dev_labels), router.predict(dev_frame))
        log.append({**config, "dev_macro_f1": round(float(score), 6)})
        if score > best_score:
            best_score, best = score, config
    if best is None:
        raise RuntimeError("Empty hyperparameter grid.")
    return best, log


def fit_refit_evaluate(
    make_router,
    frame: pd.DataFrame,
    *,
    split_column: str = "split",
    label_column: str = "oracle_label",
    grid: Sequence[Mapping[str, object]] = DEFAULT_CONFIG_GRID,
) -> tuple[object, Mapping[str, object], list[dict[str, object]], pd.DataFrame]:
    """Dev-tuned, train+dev-refit, single-shot test evaluation.

    Returns ``(fitted_router, best_config, search_log, test_predictions)``.
    """
    train = frame[frame[split_column] == "train"]
    dev = frame[frame[split_column] == "dev"]
    test = frame[frame[split_column] == "test"]
    if len(train) == 0 or len(dev) == 0 or len(test) == 0:
        raise ValueError(
            f"Split column {split_column!r} must produce non-empty train/dev/test "
            f"(got {len(train)}/{len(dev)}/{len(test)})"
        )
    best, log = select_on_dev(
        make_router, train, train[label_column].tolist(), dev, dev[label_column].tolist(), grid=grid
    )
    refit_frame = pd.concat([train, dev], axis=0)
    router = make_router(**best)
    router.fit(refit_frame, refit_frame[label_column].tolist())
    predictions = pd.DataFrame(
        {
            "problem_uid": test["problem_uid"].tolist() if "problem_uid" in test.columns else list(test.index),
            "oracle_label": test[label_column].tolist(),
            "predicted_label": router.predict(test),
        }
    )
    return router, best, log, predictions
