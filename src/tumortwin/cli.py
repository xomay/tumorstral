"""Command-line entry point; all configured paths resolve relative to project_root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import tomllib

from .data.inspectumours import download


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible preclinical and human tumour forecasting")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="Fetch pinned upstream example and license")
    fetch.add_argument("--destination", type=Path, default=Path("data/raw"))
    eda = commands.add_parser("eda", help="Quality audit and exploratory analysis")
    eda.add_argument("--config", type=Path, default=Path("configs/exploration.toml"))
    eda.add_argument("--input", type=Path)
    eda.add_argument("--processed", type=Path)
    eda.add_argument("--reports", type=Path)
    baselines = commands.add_parser("baselines", help="Evaluate individual growth models on preclinical trajectories")
    baselines.add_argument("action", choices=["split", "develop", "freeze", "evaluate"])
    baselines.add_argument("--config", type=Path, default=Path("configs/baselines.toml"))
    human = commands.add_parser("human", help="Human Laleh baselines and zero-shot Timestral")
    human.add_argument("action", choices=["download", "audit", "split", "develop", "freeze", "evaluate"])
    human.add_argument("--config", type=Path, default=Path("configs/human.toml"))
    arguments = sys.argv[1:]
    # Historical experiment commands remain readable without cluttering public help.
    if arguments:
        arguments[0] = {"phase2": "baselines", "phase3": "human"}.get(arguments[0], arguments[0])
    args = parser.parse_args(arguments)
    try:
        if args.command == "download":
            print(download(args.destination))
            return
        if args.command == "human":
            from .evaluation.human import design, freeze_human, run_human

            if args.action == "download":
                from .data.laleh import download_laleh
                from .timestral.download import download_model

                cfg = tomllib.loads(args.config.read_text())
                root = (args.config.resolve().parent/cfg["project_root"]).resolve()
                print(download_laleh((root/cfg["input"]).parent))
                if cfg["timestral"]["enabled"]:
                    print(download_model(root/cfg["timestral"]["local_model"]))
            elif args.action in {"audit", "split"}:
                _, run, _, _, split = design(args.config)
                print(json.dumps({"run": str(run), "partitions": split.partition.value_counts().to_dict()}))
            elif args.action == "freeze":
                print(freeze_human(args.config))
            else:
                print(run_human(args.config, "development" if args.action == "develop" else "test"))
            return
        if args.command == "baselines":
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
