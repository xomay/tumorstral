"""Public command names and compatibility with saved experiment scripts."""

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from tumortwin.cli import main


def test_public_help_describes_workflows_without_numbered_phases():
    result = subprocess.run([sys.executable, "-m", "tumortwin.cli", "--help"],
                             capture_output=True, text=True, check=True)
    assert "baselines" in result.stdout and "human" in result.stdout
    assert "phase" not in result.stdout.lower()
    assert Path("configs/exploration.toml").exists()
    assert Path("configs/baselines.toml").exists()


@pytest.mark.parametrize("command", ["baselines", "phase2"])
def test_baseline_command_and_historical_alias_reach_same_experiment(monkeypatch, capsys, command):
    calls = []

    def prepared(config):
        calls.append(config)
        return {}, Path("example-run"), None, pd.DataFrame({"partition": ["test"]}), {}

    monkeypatch.setattr("tumortwin.evaluation.experiment.prepare", prepared)
    monkeypatch.setattr(sys, "argv", ["tumortwin", command, "split"])
    main()
    assert calls == [Path("configs/baselines.toml")]
    assert json.loads(capsys.readouterr().out)["partitions"] == {"test": 1}
