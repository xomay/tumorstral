"""Original human lesion workbook, explicit dates and diameter-derived volumes.

No whole-dataset normalization is used. Textual censored readings are preserved
and remain missing numerically. Anonymized arms are not mapped to invented drugs.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import numpy as np
import pandas as pd

ARTICLE_URL = "https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009822"
SOURCE_URL = ("https://journals.plos.org/ploscompbiol/article/file?"
              "id=10.1371/journal.pcbi.1009822.s006&type=supplementary")
FIGSHARE_URL = "https://api.figshare.com/v2/articles/19125237"
FILENAME = "journal.pcbi.1009822.s006.xlsx"
EXPECTED_SHA256 = "ffca72e8b9a54129d2245c315ba89d8169e63dbd2c971119a63f454e5fe63e3d"
SOURCE_COLUMNS = ["Patient_Anonmyized", "Treatment_Day", "TargetLesionLongDiam_mm", "Study_Arm"]
MISSING = {"", "NA", "N/A", "NaN", "nan", "NULL", "null"}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest() -> dict:
    return dict(dataset="Laleh et al. 2022, original public S1 Data", article=ARTICLE_URL,
                supplement_doi="10.1371/journal.pcbi.1009822.s006",
                files=[dict(file=FILENAME, url=SOURCE_URL, sha256=EXPECTED_SHA256)],
                source_time="Treatment_Day: signed days relative to treatment",
                source_measure="TargetLesionLongDiam_mm: longest lesion diameter in mm",
                transformation="tumour_volume = 0.5 * diameter_mm**3; no global normalization",
                volume_unit="mm^3 (diameter-derived proxy, not segmented anatomical volume)")


def download_laleh(destination: Path) -> Path:
    """Fetch an exact public supplement; a verified local copy works offline."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination/FILENAME
    if target.exists():
        if _sha256(target.read_bytes()) != EXPECTED_SHA256:
            raise ValueError(f"Existing Laleh workbook differs from pinned supplement: {target}")
    else:
        try:
            with urlopen(SOURCE_URL, timeout=60) as response:
                payload = response.read()
        except (URLError, TimeoutError):
            with urlopen(FIGSHARE_URL, timeout=30) as response:
                item = json.load(response)
            candidates = [f for f in item["files"] if f["name"] == FILENAME]
            if len(candidates) != 1:
                raise ValueError("Official mirror does not expose the expected supplement")
            with urlopen(candidates[0]["download_url"], timeout=60) as response:
                payload = response.read()
        if _sha256(payload) != EXPECTED_SHA256:
            raise ValueError("Downloaded Laleh supplement does not match pinned SHA-256")
        with target.open("xb") as output:
            output.write(payload)
    manifest = destination/"provenance.json"
    content = json.dumps(_manifest(), indent=2, ensure_ascii=False)+"\n"
    if manifest.exists() and manifest.read_text(encoding="utf-8") != content:
        raise ValueError(f"Existing Laleh provenance differs: {manifest}")
    if not manifest.exists():
        manifest.write_text(content, encoding="utf-8")
    return target


def load_laleh(path: Path) -> tuple[pd.DataFrame, dict]:
    """Preserve all rows, original columns and source Excel coordinates.

    animal_id is a compatibility alias for the source patient identifier.
    patient_id is not prefixed by study: repeated IDs have unproven independence.
    """
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Laleh input must be the original .xlsx workbook")
    payload_hash = _sha256(path.read_bytes())
    manifest_path = path.parent/"provenance.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        matches = [f for f in manifest.get("files", []) if f.get("file") == path.name]
        if not matches or matches[0]["sha256"] != payload_hash:
            raise ValueError("Laleh workbook checksum differs from provenance manifest")
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False, engine="openpyxl")
    frames, sheet_counts = [], {}
    for sheet, source in sheets.items():
        missing = sorted(set(SOURCE_COLUMNS)-set(source.columns))
        if missing:
            raise ValueError(f"Laleh sheet {sheet!r} lacks columns: {missing}")
        if source.empty:
            continue
        frame = source.copy()
        frame["source_sheet"] = sheet
        frame["source_excel_row"] = np.arange(2, len(frame)+2)
        frame["study"] = str(sheet)
        frame["animal_id"] = source.Patient_Anonmyized.astype("string").str.strip()
        frame["patient_id"] = frame.animal_id
        frame["group"] = source.Study_Arm.astype("string").str.strip()
        frame["treatment"] = frame.group
        frame["day"] = source.Treatment_Day
        token = source.TargetLesionLongDiam_mm.astype("string").str.strip()
        diameter = pd.to_numeric(token, errors="coerce").astype(float)
        frame["diameter_mm"] = diameter.where(np.isfinite(diameter))
        frame["diameter_status"] = "observed"
        frame.loc[token.isin(MISSING), "diameter_status"] = "missing"
        frame.loc[~token.isin(MISSING) & ~np.isfinite(diameter), "diameter_status"] = "non_numeric"
        frame.loc[token.eq("TOO SMALL TO MEASURE"), "diameter_status"] = "too_small_to_measure"
        frame.loc[token.eq("NOT EVALUABLE"), "diameter_status"] = "not_evaluable"
        frame.loc[diameter.lt(0), "diameter_status"] = "negative"
        with np.errstate(over="ignore", invalid="ignore"):
            volume = .5*diameter**3
        frame["tumour_volume"] = volume.where(np.isfinite(volume))
        frame["volume_unit"] = "mm^3_proxy"
        frame["time_unit"] = "day_relative_to_treatment"
        frames.append(frame)
        sheet_counts[str(sheet)] = len(source)
    if not frames:
        raise ValueError("Laleh workbook contains no observations")
    result = pd.concat(frames, ignore_index=True)
    per_id_studies = result.groupby("patient_id", dropna=False).study.nunique()
    repeated = per_id_studies.loc[per_id_studies > 1].index
    result["cross_study_identifier"] = result.patient_id.isin(repeated)
    from .quality import normalize

    audited = normalize(result)
    metadata = dict(
        dataset="Laleh et al. 2022, original public S1 Data", article=ARTICLE_URL,
        source=str(path.resolve()), source_sha256=payload_hash,
        source_columns=SOURCE_COLUMNS, source_sheets=sheet_counts,
        n_rows=len(result), n_patient_study_pairs=int(result.groupby(["study", "patient_id"]).ngroups),
        n_source_patient_identifiers=int(result.patient_id.nunique()),
        n_cross_study_identifiers=len(repeated),
        n_numeric_eligible_rows=int(audited.analysis_eligible.sum()),
        diameter_status_counts={str(k): int(v) for k, v in Counter(result.diameter_status).items()},
        row_flags={c: int(audited[c].sum()) for c in ["missing_day", "invalid_day", "duplicate_time",
                                                    "missing_identity", "metadata_conflict", "negative_volume"]},
        time_unit="day_relative_to_treatment", volume_unit="mm^3_proxy",
        volume_formula="0.5 * TargetLesionLongDiam_mm**3",
        normalization="none; published whole-dataset normalization is not used",
        target_definition="one designated target lesion per patient; not total tumour burden",
        identity="study + original patient identifier; cross-study identifiers have unproven independence",
        limitations=["Diameter-derived proxy assumes lesion geometry; not segmented volume.",
                     "Anonymized arm labels do not identify drugs without a study dictionary.",
                     "NOT EVALUABLE and TOO SMALL TO MEASURE are not zero volumes.",
                     "Repeated IDs across studies may be shared people or anonymization collisions."])
    return result, metadata
