import base64
import io
import json

import pandas as pd
import pytest

from tumortwin.data.inspectumours import COLUMNS, download, load_raw, sha256
from tumortwin.data.quality import animal_summary, normalize, quality_report


def test_identity_missing_and_real_days(sample):
    original = sample.copy(deep=True)
    df = normalize(sample)
    pd.testing.assert_frame_equal(sample, original)
    assert len(df) == 7
    assert df.missing_tumour_volume.sum() == 1
    assert df.analysis_eligible.sum() == 6
    assert df.loc[2, "day"] == 5
    assert pd.isna(df.loc[2, "tumour_volume"])
    animals = animal_summary(df)
    assert list(animals.n_rows) == [4, 3]
    assert list(animals.n_observed) == [3, 3]
    assert list(animals.followup_days) == [9, 6]
    assert list(animals.irregular) == [True, False]
    assert set(animals.animal_id) == {"001"}


def test_followup_with_missing_endpoint_and_unsorted(sample):
    sample.loc[3, "tumour_volume"] = float("nan")
    df = normalize(sample.iloc[::-1])
    animals = animal_summary(df)
    assert animals.iloc[0].followup_days == 9
    assert animals.iloc[0].observed_followup_days == 2
    assert animals.iloc[0].short_history
    assert animals.input_unsorted.all()


@pytest.mark.parametrize("value,flag", [
    ("bad", "invalid_tumour_volume"), ("inf", "invalid_tumour_volume"),
    ("-inf", "invalid_tumour_volume"), ("", "missing_tumour_volume"),
    ("NA", "missing_tumour_volume"), (-1, "negative_volume"),
])
def test_volume_flags(sample, value, flag):
    sample["tumour_volume"] = sample.tumour_volume.astype(object)
    sample.loc[0, "tumour_volume"] = value
    df = normalize(sample)
    assert df.loc[0, flag]
    assert not df.loc[0, "analysis_eligible"]
    assert df.loc[0, "raw_tumour_volume"] == value


def test_zero_and_negative_day_are_preserved(sample):
    sample.loc[0, "tumour_volume"] = 0
    sample.loc[0, "day"] = -2
    df = normalize(sample)
    assert df.loc[0, "analysis_eligible"]
    assert df.loc[0, "day"] == -2


def test_duplicate_times_not_silently_averaged(sample):
    sample = pd.concat([sample, sample.iloc[[0]]], ignore_index=True)
    sample.loc[7, "tumour_volume"] = 999
    df = normalize(sample)
    assert df.duplicate_time.sum() == 2
    assert not df.loc[[0, 7], "analysis_eligible"].any()
    assert len(df) == 8
    assert animal_summary(df).iloc[0].n_observed == 2


def test_conflicting_treatment_quarantines_animal(sample):
    sample.loc[0, "treatment"] = "Drug X"
    df = normalize(sample)
    assert df.metadata_conflict.sum() == 4
    assert not df.loc[:3, "analysis_eligible"].any()
    assert df.loc[4:, "analysis_eligible"].all()


def test_invalid_dates_and_missing_identifiers(sample):
    sample["day"] = sample.day.astype(object)
    sample.loc[0, "day"] = "invalid"
    sample.loc[1, "day"] = ""
    sample.loc[2, "animal_id"] = None
    df = normalize(sample)
    assert df.loc[0, "invalid_day"]
    assert df.loc[1, "missing_day"]
    assert df.loc[2, "missing_identity"]
    assert not df.loc[:2, "analysis_eligible"].any()


def test_missing_metadata_is_retained(sample):
    sample.loc[:3, "treatment"] = None
    df = normalize(sample)
    assert df.missing_metadata.sum() == 4
    assert len(animal_summary(df)) == 2


def test_all_missing_identities(sample):
    sample["animal_id"] = None
    df = normalize(sample)
    animals = animal_summary(df)
    assert animals.empty
    assert quality_report(df, animals)["n_animals"] == 0


def test_csv_preserves_ids_and_missing_fields(tmp_path, sample):
    path = tmp_path / "input.csv"
    sample.to_csv(path, index=False)
    df = normalize(load_raw(path))
    assert df.animal_id.iloc[0] == "001"
    assert df.missing_tumour_volume.sum() == 1
    assert list(df.source_row) == list(range(1, 8))


def test_invalid_schema_and_empty_file(tmp_path, sample):
    path = tmp_path / "input.csv"
    sample.drop(columns="day").to_csv(path, index=False)
    with pytest.raises(ValueError, match="Missing required columns"):
        load_raw(path)
    pd.DataFrame(columns=COLUMNS).to_csv(path, index=False)
    with pytest.raises(ValueError, match="no observations"):
        load_raw(path)


def test_download_pinned_integrity_and_no_silent_overwrite(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return io.BytesIO(json.dumps({"content": base64.b64encode(b"fixture").decode()}).encode())

    monkeypatch.setattr("tumortwin.data.inspectumours.urlopen", fake_urlopen)
    path = download(tmp_path)
    assert path.read_bytes() == b"fixture"
    manifest = json.loads((tmp_path / "provenance.json").read_text())
    assert manifest["files"][0]["sha256"] == sha256(path)
    assert all(manifest["revision"] in url for url in calls)
    download(tmp_path)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differs from pinned"):
        download(tmp_path)


def test_rda_roundtrip(tmp_path, sample):
    import rdata

    path = tmp_path / "example.rda"
    # Exercise actual R serialization rather than mocking the loader.
    rdata.write_rda(path, {"example_data": sample})
    result = load_raw(path)
    assert list(result.columns) == COLUMNS
    assert len(result) == len(sample)
    assert result.animal_id.iloc[0] == "001"
    assert result.tumour_volume.isna().sum() == 1


def test_rda_wrong_object(tmp_path, sample):
    import rdata

    path = tmp_path / "wrong.rda"
    rdata.write_rda(path, {"other": sample})
    with pytest.raises(ValueError, match="example_data"):
        load_raw(path)
