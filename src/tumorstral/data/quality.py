"""Explicit row-level quality flags without imputation or silent deletion."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .inspectumours import COLUMNS, IDENTITY

MISSING_TOKENS = {"", "NA", "N/A", "NaN", "nan", "NULL", "null"}


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    df = raw.copy().reset_index(drop=True)
    if df.empty:
        raise ValueError("Dataset contains no observations")
    df.insert(0, "source_row", np.arange(1, len(df) + 1))
    for col in COLUMNS:
        df[f"raw_{col}"] = df[col]
        values = df[col].astype("string").str.strip()
        df[col] = values.mask(values.isin(MISSING_TOKENS))
    for col in ["day", "tumour_volume"]:
        values = pd.to_numeric(df[col], errors="coerce").astype(float)
        df[f"missing_{col}"] = df[col].isna()
        df[f"invalid_{col}"] = ~df[f"missing_{col}"] & ~np.isfinite(values)
        df[col] = values.where(np.isfinite(values))
    df["negative_volume"] = df.tumour_volume.lt(0)
    df["missing_identity"] = df[IDENTITY].isna().any(axis=1)
    df["missing_metadata"] = df[["group", "treatment"]].isna().any(axis=1)
    df["duplicate_time"] = (
        df.duplicated(IDENTITY + ["day"], keep=False)
        & ~df.missing_identity & df.day.notna()
    )
    df["metadata_conflict"] = False
    for _, rows in df.loc[~df.missing_identity].groupby(IDENTITY, sort=True):
        if any(rows[c].nunique(dropna=False) > 1 for c in ["group", "treatment"]):
            df.loc[rows.index, "metadata_conflict"] = True
    df["analysis_eligible"] = ~df[[
        "missing_day", "invalid_day", "missing_tumour_volume", "invalid_tumour_volume",
        "negative_volume", "missing_identity", "missing_metadata", "duplicate_time",
        "metadata_conflict",
    ]].any(axis=1)
    return df


def animal_summary(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for key, rows in df.loc[~df.missing_identity].groupby(IDENTITY, sort=True):
        days = np.sort(rows.day.dropna().unique())
        gaps = np.diff(days)
        usable = rows.loc[rows.analysis_eligible]
        observed = usable.day.to_numpy()
        records.append(dict(
            zip(IDENTITY, key, strict=True),
            group=" | ".join(sorted(rows.group.dropna().unique())),
            treatment=" | ".join(sorted(rows.treatment.dropna().unique())),
            n_rows=len(rows), n_recorded_days=len(days), n_observed=len(usable),
            n_missing_volume=int(rows.missing_tumour_volume.sum()),
            n_duplicate_rows=int(rows.duplicate_time.sum()),
            first_day=float(days[0]) if len(days) else np.nan,
            last_day=float(days[-1]) if len(days) else np.nan,
            followup_days=float(days[-1] - days[0]) if len(days) else np.nan,
            observed_followup_days=float(np.ptp(observed)) if len(observed) else np.nan,
            min_gap_days=float(gaps.min()) if len(gaps) else np.nan,
            max_gap_days=float(gaps.max()) if len(gaps) else np.nan,
            irregular=bool(len(gaps) > 1 and not np.allclose(gaps, gaps[0])),
            input_unsorted=bool((rows.day.dropna().diff().dropna() < 0).any()),
            short_history=len(usable) < 3,
        ))
    return pd.DataFrame(records, columns=[
        *IDENTITY, "group", "treatment", "n_rows", "n_recorded_days", "n_observed",
        "n_missing_volume", "n_duplicate_rows", "first_day", "last_day", "followup_days",
        "observed_followup_days", "min_gap_days", "max_gap_days", "irregular",
        "input_unsorted", "short_history",
    ])


def quality_report(df: pd.DataFrame, animals: pd.DataFrame) -> dict:
    flags = [c for c in df.columns if c.startswith(("missing_", "invalid_"))]
    flags += ["negative_volume", "duplicate_time", "metadata_conflict", "analysis_eligible"]
    return {
        "n_rows": len(df), "n_animals": len(animals),
        "n_studies": int(df.study.nunique()),
        "row_flags": {c: int(df[c].sum()) for c in flags},
        "n_irregular_animals": int(animals.irregular.sum()),
        "n_short_histories_lt3": int(animals.short_history.sum()),
        "n_unsorted_animals": int(animals.input_unsorted.sum()),
        "units": {"day": "days after implantation", "tumour_volume": "mm^3"},
        "identity": IDENTITY,
        "policy": "All source rows retained; only analysis_eligible rows enter volume summaries. "
                  "Duplicate animal-days and conflicting metadata excluded, never averaged. "
                  "Follow-up uses recorded dates including missing volumes. No resampling or imputation. "
                  "Absent visits cannot be inferred without a planned visit schedule.",
    }
