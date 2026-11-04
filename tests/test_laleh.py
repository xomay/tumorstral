"""Synthetic workbooks and network mocks only; no human records in fixtures."""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tumortwin.data.laleh import FILENAME, SOURCE_COLUMNS, download_laleh, load_laleh


def write_fixture(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


@pytest.fixture
def synthetic():
    return pd.DataFrame({
        "Patient_Anonmyized": ["900719925474099312345"]*5,
        "Treatment_Day": [-12, 42, 85, 126, 169],
        "TargetLesionLongDiam_mm": [10, 8, "TOO SMALL TO MEASURE", "NOT EVALUABLE", 0],
        "Study_Arm": ["Synthetic_Arm"]*5,
    })


def test_original_units_dates_censored_values_and_source_rows(tmp_path, synthetic):
    path = write_fixture(tmp_path/"synthetic.xlsx", {"SyntheticStudy": synthetic})
    frame, metadata = load_laleh(path)
    assert len(frame) == 5
    assert frame.patient_id.eq("900719925474099312345").all()
    assert frame.animal_id.equals(frame.patient_id)
    assert frame.day.tolist() == ["-12", "42", "85", "126", "169"]
    np.testing.assert_allclose(frame.tumour_volume, [500., 256., np.nan, np.nan, 0.], equal_nan=True)
    assert frame.TargetLesionLongDiam_mm.iloc[2] == "TOO SMALL TO MEASURE"
    assert frame.diameter_status.tolist() == ["observed", "observed", "too_small_to_measure", "not_evaluable", "observed"]
    assert frame.source_excel_row.tolist() == [2, 3, 4, 5, 6]
    assert frame.source_sheet.eq("SyntheticStudy").all()
    assert metadata["volume_unit"] == "mm^3_proxy"
    assert metadata["normalization"].startswith("none;")
    assert metadata["n_numeric_eligible_rows"] == 3


def test_cross_study_identifiers_are_not_disguised_as_independent(tmp_path, synthetic):
    second = synthetic.iloc[:2].copy()
    second.Study_Arm = "Synthetic_Arm_B"
    path = write_fixture(tmp_path/"synthetic.xlsx", {"S1": synthetic, "S2": second})
    frame, metadata = load_laleh(path)
    assert metadata["n_cross_study_identifiers"] == 1
    assert metadata["n_patient_study_pairs"] == 2
    assert metadata["n_source_patient_identifiers"] == 1
    assert frame.cross_study_identifier.all()
    assert frame.patient_id.nunique() == 1


def test_invalid_diameters_and_missing_dates_are_retained(tmp_path, synthetic):
    synthetic["TargetLesionLongDiam_mm"] = ["", "inf", -2, "text", 0]
    synthetic.loc[0, "Treatment_Day"] = None
    path = write_fixture(tmp_path/"synthetic.xlsx", {"S": synthetic})
    frame, metadata = load_laleh(path)
    assert len(frame) == 5
    assert frame.diameter_status.tolist() == ["missing", "non_numeric", "negative", "non_numeric", "observed"]
    assert frame.tumour_volume.iloc[2] == -4
    assert frame.tumour_volume.iloc[4] == 0
    assert metadata["row_flags"]["missing_day"] == 1
    assert metadata["row_flags"]["negative_volume"] == 1


def test_duplicate_patient_days_remain_flagged(tmp_path, synthetic):
    frame = pd.concat([synthetic, synthetic.iloc[[0]]], ignore_index=True)
    path = write_fixture(tmp_path/"synthetic.xlsx", {"S": frame})
    data, metadata = load_laleh(path)
    assert len(data) == 6
    assert metadata["row_flags"]["duplicate_time"] == 2


def test_schema_and_empty_dataset(tmp_path, synthetic):
    path = write_fixture(tmp_path/"synthetic.xlsx", {"S": synthetic.drop(columns="Treatment_Day")})
    with pytest.raises(ValueError, match="lacks columns"):
        load_laleh(path)
    write_fixture(path, {"S": pd.DataFrame(columns=SOURCE_COLUMNS)})
    with pytest.raises(ValueError, match="no observations"):
        load_laleh(path)


def test_provenance_changes_rejected(tmp_path, synthetic):
    path = write_fixture(tmp_path/"synthetic.xlsx", {"S": synthetic})
    (tmp_path/"provenance.json").write_text(json.dumps({
        "files": [{"file": path.name, "sha256": "bad"}]}))
    with pytest.raises(ValueError, match="checksum"):
        load_laleh(path)


def test_download_is_pinned_cached_and_immutable(tmp_path, monkeypatch):
    payload = b"explicitly synthetic download fixture"
    expected = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr("tumortwin.data.laleh.EXPECTED_SHA256", expected)
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr("tumortwin.data.laleh.urlopen", fetch)
    path = download_laleh(tmp_path)
    assert path.name == FILENAME and path.read_bytes() == payload
    assert len(calls) == 1
    download_laleh(tmp_path)
    assert len(calls) == 1  # verified local data work without network
    manifest = json.loads((tmp_path/"provenance.json").read_text())
    assert manifest["files"][0]["sha256"] == expected
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differs"):
        download_laleh(tmp_path)


def test_wrong_download_never_writes_a_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr("tumortwin.data.laleh.urlopen", lambda *a, **kw: io.BytesIO(b"unexpected"))
    with pytest.raises(ValueError, match="SHA-256"):
        download_laleh(tmp_path)
    assert not (tmp_path/FILENAME).exists()
