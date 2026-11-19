import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from tumorstral.data.inspectumours import sha256
from tumorstral.data.quality import normalize
from tumorstral.eda import run_eda, treatment_time_summary


def test_summaries_at_actual_dates(sample):
    summary = treatment_time_summary(normalize(sample))
    assert set(summary.loc[summary.study == "S1", "day"]) == {0, 2, 9}
    assert summary.n_animals.eq(1).all()
    assert summary.loc[(summary.study == "S1") & (summary.day == 9), "median"].iloc[0] == 20


def test_complete_offline_pipeline_and_cli(tmp_path, sample):
    source = tmp_path / "synthetic.csv"
    sample.to_csv(source, index=False)
    before = source.read_bytes()
    config = tmp_path / "exploration.toml"
    config.write_text('project_root = "."\ninput = "synthetic.csv"\n'
                      'processed = "processed"\nreports = "reports"\n')
    result = subprocess.run([sys.executable, "-m", "tumorstral.cli", "eda",
                             "--config", str(config)], capture_output=True, text=True,
                             env={**os.environ, "MPLCONFIGDIR": str(tmp_path / "mpl")})
    assert result.returncode == 0, result.stderr
    quality = json.loads(result.stdout)
    assert quality["n_animals"] == 2
    assert quality["n_rows"] == 7
    assert source.read_bytes() == before
    processed = pd.read_csv(tmp_path / "processed/observations.csv")
    assert len(processed) == 7
    assert processed.analysis_eligible.sum() == 6
    provenance = json.loads((tmp_path / "reports/provenance.json").read_text())
    assert provenance["sha256"] == sha256(source)
    report = (tmp_path / "reports/exploration.md").read_text()
    assert "[EDA](glossary.md#eda)" in report
    glossary = (tmp_path / "reports/glossary.md").read_text()
    assert "## EDA" in glossary
    assert "## SHA-256" in glossary
    assert "1462" not in report  # no hard-coded experimental results
    for name in ["distributions", "observation_gaps", "individual_trajectories", "treatment_comparison"]:
        assert (tmp_path / f"reports/figures/{name}.png").stat().st_size > 1000
    assert (tmp_path / "reports/treatment_summary.csv").exists()


def test_provenance_tampering_rejected(tmp_path, sample):
    source = tmp_path / "synthetic.csv"
    sample.to_csv(source, index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({
        "files": [{"file": source.name, "sha256": "incorrect"}]}))
    with pytest.raises(ValueError, match="checksum"):
        run_eda(source, tmp_path / "processed", tmp_path / "reports")
    assert not (tmp_path / "processed").exists()


def test_input_cannot_be_overwritten(tmp_path, sample):
    source = tmp_path / "observations.csv"
    sample.to_csv(source, index=False)
    with pytest.raises(ValueError, match="overwrite"):
        run_eda(source, tmp_path, tmp_path / "reports")


def test_fully_unusable_dataset_still_has_quality_report(tmp_path, sample):
    sample["animal_id"] = None
    source = tmp_path / "synthetic.csv"
    sample.to_csv(source, index=False)
    quality = run_eda(source, tmp_path / "processed", tmp_path / "reports")
    assert quality["n_animals"] == 0
    assert quality["row_flags"]["analysis_eligible"] == 0
