"""Command-line entry point; all configured paths resolve relative to project_root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

from .data.inspectumours import download


def main() -> None:
    parser = argparse.ArgumentParser(description="TumorTwin — phases 1 et 2")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="Fetch pinned upstream example and license")
    fetch.add_argument("--destination", type=Path, default=Path("data/raw"))
    eda = commands.add_parser("eda", help="Quality audit and exploratory analysis")
    eda.add_argument("--config", type=Path, default=Path("configs/phase1.toml"))
    eda.add_argument("--input", type=Path)
    eda.add_argument("--processed", type=Path)
    eda.add_argument("--reports", type=Path)
    phase2 = commands.add_parser("phase2", help="Split, development, freeze and final baseline evaluation")
    phase2.add_argument("action", choices=["split", "develop", "freeze", "evaluate"])
    phase2.add_argument("--config", type=Path, default=Path("configs/phase2.toml"))
    args = parser.parse_args()
    try:
        if args.command == "download":
            print(download(args.destination))
            return
        if args.command == "phase2":
            from .evaluation.experiment import freeze, prepare, run_partition

            if args.action == "split":
                _, run, _, split, _ = prepare(args.config)
                print(json.dumps({"run": str(run), "partitions": split.partition.value_counts().to_dict()}))
            elif args.action == "freeze":
                print(freeze(args.config))
            else:
                partition = "development" if args.action == "develop" else "test"
                print(run_partition(args.config, partition))
            return
        with args.config.open("rb") as file:
            config = tomllib.load(file)
        root = (args.config.resolve().parent / config.get("project_root", "..")).resolve()
        source = args.input or root / config["input"]
        processed = args.processed or root / config["processed"]
        reports = args.reports or root / config["reports"]
        from .eda import run_eda

        print(json.dumps(run_eda(source, processed, reports), indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"tumortwin: {error}\n")


if __name__ == "__main__":
    main()
