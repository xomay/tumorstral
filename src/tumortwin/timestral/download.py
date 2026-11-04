"""Pinned public 5M model artifacts, checked before offline inference."""

import json
from pathlib import Path
from urllib.request import urlopen

from ..data.inspectumours import sha256

MODEL_REVISION = "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"
CODE_REVISION = "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
HASHES = {
    "config.json": "b5f27f61513f8fd1a3aa996f3720d3679cb40bce5bcb08eb3dc320ce726e7c2f",
    "model.safetensors": "7ace108c4987e7f2a99a75a445240019d1d31c2117139d1bd05ffdfd25aca738",
    "LICENSE": "648194727930df730890e9f9affdbcc5c930d406d6829559b25ca3d5a973fc8c",
}


def download_model(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    import hashlib

    for name, expected in HASHES.items():
        target = destination/name
        if not target.exists():
            url = f"https://huggingface.co/mistralai/Timestral-5M/resolve/{MODEL_REVISION}/{name}"
            with urlopen(url, timeout=60) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"Downloaded model checksum differs: {name}")
            with target.open("xb") as stream:
                stream.write(payload)
        if sha256(target) != expected:
            raise ValueError(f"Existing model checksum differs: {name}")
    manifest = dict(repository="mistralai/Timestral-5M", model_revision=MODEL_REVISION,
                    code_revision=CODE_REVISION, files=HASHES)
    path = destination/"provenance.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Model provenance differs from pinned artifacts")
    if not path.exists():
        path.write_text(json.dumps(manifest, indent=2)+"\n")
    return destination
