"""Download the upstream example at an immutable commit and read its schema."""

from __future__ import annotations

import hashlib
import base64
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

REVISION = "eb41f4f80595b7185cf925a3195d35e1e3b34394"
COLUMNS = ["study", "group", "treatment", "animal_id", "day", "tumour_volume"]
IDENTITY = ["study", "animal_id"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(destination: Path) -> Path:
    """Keep upstream data and license together; never overwrite an existing file."""
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for remote, local in [("data/example_data.rda", "example_data.rda"),
                          ("man/example_data.Rd", "example_data.Rd"),
                          ("LICENSE.md", "LICENSE.upstream.md")]:
        target = destination / local
        url = (f"https://api.github.com/repos/AstraZeneca/INSPECTumours/contents/"
               f"{remote}?ref={REVISION}")
        # Verify existing files against this revision, rather than trusting a cache.
        with urlopen(url, timeout=60) as response:
            payload = base64.b64decode(json.load(response)["content"], validate=False)
        digest = hashlib.sha256(payload).hexdigest()
        if target.exists() and sha256(target) != digest:
            raise ValueError(f"Existing file differs from pinned upstream: {target}")
        if not target.exists():
            target.write_bytes(payload)
        records.append({"file": local, "url": url, "sha256": digest})
    manifest = {"repository": "https://github.com/AstraZeneca/INSPECTumours",
                "revision": REVISION, "files": records}
    (destination / "provenance.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination / "example_data.rda"


def load_raw(path: Path) -> pd.DataFrame:
    """Read RDA or an exact-schema CSV; preserve identifier strings and raw fields."""
    if path.suffix.lower() in {".rda", ".rdata"}:
        import rdata

        objects = rdata.read_rda(path)
        if "example_data" not in objects:
            raise ValueError("RDA must contain the object 'example_data'")
        frame = objects["example_data"]
        if not isinstance(frame, pd.DataFrame):
            raise ValueError("example_data must be a data frame")
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    else:
        raise ValueError("Expected .rda, .rdata or .csv")
    missing = sorted(set(COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}; found {list(frame.columns)}")
    if frame.empty:
        raise ValueError("Dataset contains no observations")
    return frame.reset_index(drop=True)
