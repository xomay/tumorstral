"""Temporal registries and deterministic animal allocation, without target leakage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.inspectumours import IDENTITY
from ..data.quality import normalize


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def make_split(raw: pd.DataFrame, seed: int = 20261103, test_fraction: float = .2) -> pd.DataFrame:
    """Use identifiers/strata only; never use volumes, visits or forecast availability."""
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between zero and one")
    df = normalize(raw)
    if df.missing_identity.any() or df.missing_metadata.any() or df.metadata_conflict.any():
        raise ValueError("Split requires unambiguous animal identity and fixed metadata")
    animals = df[IDENTITY+["treatment", "group"]].drop_duplicates()
    animals["allocation_hash"] = [digest([seed, str(s), str(a)])
                                   for s, a in animals[IDENTITY].itertuples(index=False, name=None)]
    records = []
    for _, group in animals.groupby(["study", "treatment"], sort=True):
        ordered = group.sort_values("allocation_hash").copy()
        ntest = int(np.floor(len(ordered)*test_fraction))
        if ntest < 1 or ntest >= len(ordered):
            raise ValueError("Every stratum must have both development and test animals")
        ordered["partition"] = ["test"]*ntest + ["development"]*(len(ordered)-ntest)
        records.append(ordered)
    return pd.concat(records).sort_values(IDENTITY).reset_index(drop=True)


@dataclass
class Origin:
    origin_id: str
    study: str
    animal_id: str
    treatment: str
    analysis: str
    t0: float
    n_context: int
    context_days: float
    source_rows: list[int]
    days: np.ndarray
    volumes: np.ndarray
    status: str

    def record(self) -> dict:
        return {k: v for k, v in vars(self).items() if k not in {"days", "volumes"}}


def build_origins(raw: pd.DataFrame, min_history: int = 6,
                  short_histories: tuple[int, ...] = (3, 4, 5)) -> list[Origin]:
    """Recompute quality on every prefix; future metadata never filter its context."""
    raw = raw.reset_index(drop=True)
    numeric = normalize(raw)
    result = []
    for key, group in numeric.loc[~numeric.missing_identity].groupby(IDENTITY, sort=True):
        source_indices = group.index
        short_seen = set()
        for t0 in sorted(group.day.dropna().unique()):
            indices = source_indices[group.day.le(t0)]
            # Raw source indices survive normalization so source_row stays traceable.
            prefix = normalize(raw.loc[indices].reset_index(drop=True))
            valid = prefix.loc[prefix.analysis_eligible].sort_values("day")
            conflict = bool(prefix.metadata_conflict.any())
            lengths = []
            if len(valid) >= min_history or conflict:
                lengths.append("main")
            if len(valid) in short_histories and len(valid) not in short_seen:
                lengths.append(f"short_{len(valid)}")
                short_seen.add(len(valid))
            for analysis in lengths:
                status = "metadata_conflict" if conflict else "ok"
                # A non-usable visit cannot define a valid prediction origin.
                if not conflict and (valid.empty or valid.day.iloc[-1] != t0):
                    continue
                days = valid.day.to_numpy(float)
                volumes = valid.tumour_volume.to_numpy(float)
                original_rows = (raw.loc[indices, "_source_row"].to_numpy() if "_source_row" in raw
                                 else indices+1)
                source_map = dict(zip(prefix.source_row, original_rows, strict=True))
                source_rows = [int(source_map[i]) for i in valid.source_row]
                treatment = str(valid.treatment.iloc[0]) if len(valid) else "unknown"
                identifier = digest([str(key[0]), str(key[1]), float(t0), analysis])[:24]
                result.append(Origin(identifier, str(key[0]), str(key[1]), treatment, analysis,
                                     float(t0), len(valid), float(np.ptp(days)) if len(days) else 0.,
                                     source_rows, days, volumes, status))
    return result


def target_registry(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate individual dates separately from earlier contexts and later metadata."""
    raw = raw.reset_index(drop=True)
    normalized = normalize(raw)
    records = []
    dated = normalized.loc[~normalized.missing_identity & normalized.day.notna()]
    for key, group in dated.groupby(IDENTITY+["day"], sort=True):
        local = normalize(raw.loc[group.index].reset_index(drop=True))
        valid = len(local) == 1 and bool(local.analysis_eligible.iloc[0])
        records.append(dict(study=str(key[0]), animal_id=str(key[1]), target_day=float(key[2]),
                            target_volume=float(local.tumour_volume.iloc[0]) if valid else np.nan,
                            target_treatment=str(local.treatment.iloc[0]),
                            target_status="observed" if valid else "invalid_target",
                            target_source_rows=json.dumps(
                                raw.loc[group.index, "_source_row"].astype(int).tolist()
                                if "_source_row" in raw else (group.index+1).tolist())))
    return pd.DataFrame(records, columns=[*IDENTITY, "target_day", "target_volume",
                                         "target_treatment", "target_status", "target_source_rows"])


def join_targets(predictions: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    joined = predictions.merge(targets, how="left", on=IDENTITY+["target_day"], validate="many_to_one")
    joined["target_status"] = joined.target_status.fillna("no_exact_target")
    joined["future_metadata_disagreement"] = (
        joined.target_treatment.notna() & joined.treatment.ne(joined.target_treatment))
    return joined
