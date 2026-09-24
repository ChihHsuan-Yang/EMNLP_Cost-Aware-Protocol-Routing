"""Router / probe feature construction, with a structural no-leakage guard.

The central claim of the paper is about *prediction*: can a router decide, from
the problem alone, which protocol to pay for?  That claim is void if any
outcome column reaches the feature matrix.  So this module does not merely
avoid label columns by convention -- it refuses to touch them.

Design
------
* :data:`FORBIDDEN_FEATURE_COLUMNS` is an explicit set of outcome/label column
  names, plus :data:`FORBIDDEN_FEATURE_PATTERNS` for families like ``*_correct``.
* :func:`assert_no_leakage` raises :class:`LeakageError` on contact with any of
  them.  It is called by :func:`build_feature_frame` BEFORE anything is fitted
  or transformed, and by :class:`FeatureSpec` at construction time.
* The guard checks the columns actually handed to the featurizer, not a
  caller's promise about them.  Passing a whole benchmark frame is fine; naming
  a forbidden column as a feature is not.

The guard is name-based, which means it stops the mistakes people actually
make (pasting ``baseline_correct`` into a feature list, globbing ``*_correct``
into the metadata columns).  It cannot stop a caller who first renames
``baseline_correct`` to ``feature_17``; that is a deliberate act, not a slip.

Its coverage is a list of spellings, so it is only as good as that list.  An
independent audit defeated an earlier version with ``baseline_success`` -- a
plainly-named outcome column, no disguise -- because the suffix list covered
``*_correct`` and ``*_solved`` but not ``*_success``.  If you add an outcome
column with a spelling not listed here, add the spelling here too.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, OneHotEncoder, StandardScaler


class LeakageError(ValueError):
    """Raised when an outcome/label column reaches feature construction."""


#: Exact column names that must never become features.
FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        # Per-protocol outcomes (matched-label tables).
        "baseline_correct",
        "single_correct",
        "per_correct",
        "broadcast_correct",
        # Per-protocol outcomes (short-paper benchmark CSV spelling).
        "baseline_final_passed",
        "single_agent_final_passed",
        "per_final_passed",
        "broadcast_final_passed",
        # Derived labels.
        "oracle_cheapest_successful",
        "cheapest_successful_protocol",
        "oracle_label",
        "any_protocol_solved",
        # Bare outcome words. A column called simply "outcome" or "verdict" is
        # a label in every dataset the authors have seen.
        "outcome",
        "verdict",
        "failed",
        "failure",
        "success",
        "succeeded",
        "correct",
        "incorrect",
        "correctness",
        "solved",
        "result",
        "target",
        "label",
        "y",
        "y_true",
        "y_label",
        "ground_truth",
        "solved",
        "is_correct",
        "correct",
        "label",
        "gold_label",
        "y",
        # Gold answers / references.
        "answer",
        "gold",
        "gold_answer",
        "final_answer",
        "reference_answer",
        "ground_truth",
        "solution",
        # Post-hoc realised quantities.
        "predicted_success",
        "success",
    }
)

#: Regex families that must never become features.
FORBIDDEN_FEATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Outcome families, by suffix.
    re.compile(r"^.*_correct$"),
    re.compile(r"^.*_final_passed$"),
    re.compile(r"^.*_passed$"),
    re.compile(r"^.*_solved$"),
    # An independent audit smuggled a verbatim copy of ``baseline_correct``
    # through this guard under the name ``baseline_success`` -- no renaming
    # trickery, just a spelling the suffix list did not happen to cover.  The
    # families below close that gap.  The lesson generalises: enumerate the
    # vocabulary people actually use for an outcome, not only the vocabulary
    # this codebase happens to use.
    re.compile(r"^.*_success$"),
    re.compile(r"^.*_succeeded$"),
    re.compile(r"^.*_failed$"),
    re.compile(r"^.*_failure$"),
    re.compile(r"^.*_incorrect$"),
    re.compile(r"^.*_wrong$"),
    re.compile(r"^.*_score$"),
    re.compile(r"^.*_verdict$"),
    re.compile(r"^.*_outcome$"),
    re.compile(r"^.*_label$"),
    # Derived-label prefixes.
    re.compile(r"^oracle(_.*)?$"),
    re.compile(r"^gold(_.*)?$"),
    re.compile(r"^cheapest(_.*)?$"),
    re.compile(r"^first_success(_.*)?$"),
    re.compile(r"^is_(correct|wrong|failure|success|solved)$"),
)


def is_forbidden(column: str) -> bool:
    """True if ``column`` is an outcome/label column that must not be a feature."""
    name = str(column).strip().lower()
    if name in FORBIDDEN_FEATURE_COLUMNS:
        return True
    return any(pattern.match(name) for pattern in FORBIDDEN_FEATURE_PATTERNS)


def assert_no_leakage(columns: Iterable[str], *, where: str = "feature construction") -> None:
    """Raise :class:`LeakageError` if any of ``columns`` is a label column.

    This is the single choke point.  Call it with the exact column names that
    are about to be turned into features.
    """
    offending = sorted({str(c) for c in columns if is_forbidden(c)})
    if offending:
        raise LeakageError(
            f"Label leakage blocked at {where}: "
            f"{offending} may not be used as features. "
            "These columns encode protocol outcomes or gold answers; a router "
            "that sees them is not predicting anything."
        )


@dataclass(frozen=True)
class FeatureSpec:
    """Declarative description of which columns become which kind of feature.

    Validated at construction: naming a forbidden column here raises
    immediately, before any data is read.
    """

    text_column: str | None = "problem"
    categorical_columns: Sequence[str] = ("source",)
    multilabel_json_columns: Sequence[str] = ("domain",)
    numeric_columns: Sequence[str] = ("difficulty", "difficulty_tier")
    tfidf_ngram_range: tuple[int, int] = (1, 2)
    tfidf_min_df: int = 2
    tfidf_max_features: int = 20000

    def __post_init__(self) -> None:
        assert_no_leakage(self.all_columns(), where="FeatureSpec construction")

    def all_columns(self) -> list[str]:
        names: list[str] = []
        if self.text_column:
            names.append(self.text_column)
        names.extend(self.categorical_columns)
        names.extend(self.multilabel_json_columns)
        names.extend(self.numeric_columns)
        return names


#: Metadata-only variant: the paper's "metadata-only router" ablation.
METADATA_ONLY_SPEC = FeatureSpec(text_column=None)

#: Main text+metadata variant.
TEXT_METADATA_SPEC = FeatureSpec()


def _parse_json_list(raw: object) -> list[str]:
    """Parse a JSON-list-shaped metadata cell, tolerating plain strings."""
    text = "" if raw is None else str(raw)
    if not text or text.lower() == "nan":
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return [text]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def build_feature_frame(frame: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Project ``frame`` down to exactly the columns ``spec`` declares.

    Raises :class:`LeakageError` on contact with a forbidden column.  The
    returned frame is what the featurizer sees; outcome columns are physically
    absent from it, so a downstream bug cannot reach them.
    """
    assert_no_leakage(spec.all_columns(), where="build_feature_frame(spec)")
    missing = [c for c in spec.all_columns() if c not in frame.columns]
    if missing:
        raise KeyError(f"Feature columns absent from input table: {missing}")
    projected = frame.loc[:, spec.all_columns()].copy()
    # Belt and braces: the projection must not have carried a label column.
    assert_no_leakage(projected.columns, where="build_feature_frame(result)")
    return projected


@dataclass
class Featurizer:
    """Fit/transform bundle for the router feature space.

    Fitted on the training split only.  ``transform`` never re-fits, so dev and
    test cannot influence the vocabulary or the scaler statistics.
    """

    spec: FeatureSpec = field(default_factory=FeatureSpec)
    _text: TfidfVectorizer | None = field(default=None, init=False, repr=False)
    _categorical: OneHotEncoder | None = field(default=None, init=False, repr=False)
    _multilabel: dict[str, MultiLabelBinarizer] = field(default_factory=dict, init=False, repr=False)
    _scaler: StandardScaler | None = field(default=None, init=False, repr=False)
    _fitted: bool = field(default=False, init=False, repr=False)

    def fit(self, frame: pd.DataFrame) -> Featurizer:
        data = build_feature_frame(frame, self.spec)
        if self.spec.text_column:
            self._text = TfidfVectorizer(
                ngram_range=self.spec.tfidf_ngram_range,
                min_df=self.spec.tfidf_min_df,
                max_features=self.spec.tfidf_max_features,
                lowercase=True,
                strip_accents="unicode",
            )
            self._text.fit(data[self.spec.text_column].fillna("").astype(str).tolist())
        if self.spec.categorical_columns:
            self._categorical = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
            self._categorical.fit(data[list(self.spec.categorical_columns)].fillna("").astype(str))
        for column in self.spec.multilabel_json_columns:
            binarizer = MultiLabelBinarizer(sparse_output=True)
            binarizer.fit(data[column].map(_parse_json_list).tolist())
            self._multilabel[column] = binarizer
        if self.spec.numeric_columns:
            self._scaler = StandardScaler(with_mean=False)
            self._scaler.fit(self._numeric_matrix(data))
        self._fitted = True
        return self

    def _numeric_matrix(self, data: pd.DataFrame) -> np.ndarray:
        numeric = data[list(self.spec.numeric_columns)].apply(pd.to_numeric, errors="coerce")
        return numeric.fillna(0.0).to_numpy(dtype=float)

    def transform(self, frame: pd.DataFrame):
        if not self._fitted:
            raise RuntimeError("Featurizer.transform called before fit.")
        data = build_feature_frame(frame, self.spec)
        blocks = []
        if self._text is not None and self.spec.text_column:
            blocks.append(self._text.transform(data[self.spec.text_column].fillna("").astype(str).tolist()))
        if self._categorical is not None:
            blocks.append(
                self._categorical.transform(data[list(self.spec.categorical_columns)].fillna("").astype(str))
            )
        for column, binarizer in self._multilabel.items():
            known = set(binarizer.classes_.tolist())
            filtered = [[v for v in _parse_json_list(cell) if v in known] for cell in data[column]]
            blocks.append(binarizer.transform(filtered))
        if self._scaler is not None:
            numeric = self._scaler.transform(self._numeric_matrix(data))
            blocks.append(numeric if sparse.issparse(numeric) else sparse.csr_matrix(numeric))
        if not blocks:
            raise ValueError("FeatureSpec produced no feature blocks.")
        return sparse.hstack(blocks, format="csr")

    def fit_transform(self, frame: pd.DataFrame):
        return self.fit(frame).transform(frame)

    @property
    def n_features(self) -> int:
        if not self._fitted:
            raise RuntimeError("Featurizer is not fitted.")
        total = 0
        if self._text is not None:
            total += len(self._text.vocabulary_)
        if self._categorical is not None:
            total += sum(len(c) for c in self._categorical.categories_)
        total += sum(len(b.classes_) for b in self._multilabel.values())
        total += len(self.spec.numeric_columns)
        return total
