"""Reproducible exploratory tables, figures and a self-contained quality report."""

from __future__ import annotations

import importlib.metadata
from importlib.resources import files
import json
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data.inspectumours import IDENTITY, load_raw, sha256
from .data.quality import animal_summary, normalize, quality_report


def _table_markdown(df: pd.DataFrame) -> str:
    """Avoid a runtime dependency on tabulate; escape user-provided strings."""
    def cell(value: object) -> str:
        if pd.isna(value):
            return "—"
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(str, df.columns)) + " |",
             "| " + " | ".join(["---"] * len(df.columns)) + " |"]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |"
                 for row in df.itertuples(index=False, name=None))
    return "\n".join(lines)


def _save(fig: plt.Figure, folder: Path, name: str) -> None:
    fig.tight_layout()
    fig.savefig(folder / name, dpi=150)
    plt.close(fig)


def make_figures(df: pd.DataFrame, animals: pd.DataFrame, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    valid = df.loc[df.analysis_eligible]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, values, label in zip(axes,
            [animals.n_observed, animals.followup_days, valid.tumour_volume],
            ["Mesures exploitables / animal", "Suivi enregistré (jours)", "Volume (mm³)"],
            strict=True):
        ax.hist(values.dropna(), bins="auto", color="#287a85", edgecolor="white")
        ax.set(xlabel=label, ylabel="Effectif")
    _save(fig, folder, "distributions.png")

    # At each recorded date only: no alignment to visit rank, no interpolation.
    dated = df.loc[~df.missing_identity & df.day.notna()]
    dates = dated.drop_duplicates(IDENTITY + ["day"]).sort_values(IDENTITY + ["day"])
    gaps = dates.groupby(IDENTITY).day.diff().dropna()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(gaps, bins="auto", color="#7355a1", edgecolor="white")
    ax.set(xlabel="Intervalle entre jours enregistrés (jours)", ylabel="Effectif")
    _save(fig, folder, "observation_gaps.png")

    studies = sorted(df.study.dropna().unique())
    treatments = sorted(df.treatment.dropna().unique())
    if not studies or not treatments:
        studies, treatments = ["Aucune étude exploitable"], ["Aucun traitement exploitable"]
    fig, axes = plt.subplots(len(studies), len(treatments), squeeze=False,
                             figsize=(5 * len(treatments), 3.5 * len(studies)))
    # Preserve NaNs to break lines at explicitly missing / invalid observations.
    for i, study in enumerate(studies):
        for j, treatment in enumerate(treatments):
            ax = axes[i, j]
            selected = df.loc[(df.study == study) & (df.treatment == treatment)
                              & ~df.missing_identity & df.day.notna()]
            for _, trajectory in selected.groupby(IDENTITY):
                trajectory = trajectory.sort_values("day")
                ax.plot(trajectory.day,
                        trajectory.tumour_volume.where(trajectory.analysis_eligible),
                        "o-", ms=2, lw=0.8, alpha=0.6)
            ax.set(title=f"{study} · {treatment}", xlabel="Jour après implantation", ylabel="Volume (mm³)")
    _save(fig, folder, "individual_trajectories.png")

    summary = treatment_time_summary(df)
    fig, axes = plt.subplots(2, len(studies), squeeze=False, figsize=(5 * len(studies), 7))
    for j, study in enumerate(studies):
        for treatment in treatments:
            rows = summary.loc[(summary.study == study) & (summary.treatment == treatment)]
            if rows.empty:
                continue
            # Markers rather than connected means: no implied resampling.
            axes[0, j].errorbar(rows.day, rows["median"],
                yerr=np.stack([rows["median"] - rows.q25, rows.q75 - rows["median"]]),
                fmt="o", ms=3, capsize=2, label=treatment)
            axes[1, j].plot(rows.day, rows.n_animals, "o", label=treatment)
        axes[0, j].set(title=study, ylabel="Médiane et intervalle interquartile (mm³)", xlabel="Jour après implantation")
        axes[1, j].set(ylabel="Animaux mesurés à cette date", xlabel="Jour après implantation")
        if axes[0, j].has_data():
            axes[0, j].legend(fontsize=8)
    _save(fig, folder, "treatment_comparison.png")


def treatment_time_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (df.loc[df.analysis_eligible]
            .groupby(["study", "treatment", "day"], observed=True)
            .agg(n_animals=("animal_id", "nunique"), median=("tumour_volume", "median"),
                 mean=("tumour_volume", "mean"), std=("tumour_volume", "std"),
                 q25=("tumour_volume", lambda x: x.quantile(.25)),
                 q75=("tumour_volume", lambda x: x.quantile(.75)))
            .reset_index())


def run_eda(source: Path, processed: Path, reports: Path) -> dict:
    """Write outputs for all input rows; explicit flags govern descriptive summaries."""
    # Never allow an output path to overwrite the source data.
    if any(source.resolve().is_relative_to(folder.resolve()) for folder in [processed, reports]):
        raise ValueError("Output must not overwrite input data")
    raw = load_raw(source)
    df = normalize(raw)
    animals = animal_summary(df)
    quality = quality_report(df, animals)
    versions = {name: importlib.metadata.version(name)
                for name in ["tumortwin", "numpy", "pandas", "matplotlib", "rdata"]}
    provenance = {
        "source": str(source.resolve()), "sha256": sha256(source),
        "source_columns": list(raw.columns),
        "source_dtypes": {c: str(t) for c, t in raw.dtypes.items()},
        "python": platform.python_version(), "packages": versions,
        "parameters": {"short_history_threshold": 3, "imputation": False},
    }
    manifest = source.parent / "provenance.json"
    if manifest.exists():
        upstream = json.loads(manifest.read_text(encoding="utf-8"))
        matching = [r for r in upstream.get("files", []) if r["file"] == source.name]
        if matching:
            if matching[0]["sha256"] != provenance["sha256"]:
                raise ValueError("Input checksum differs from provenance manifest")
            provenance["upstream"] = upstream
    for folder in [processed, reports]:
        folder.mkdir(parents=True, exist_ok=True)
    glossary = files("tumortwin").joinpath("glossary.md").read_text(encoding="utf-8")
    (reports / "glossary.md").write_text(glossary, encoding="utf-8")
    df.to_csv(processed / "observations.csv", index=False)
    animals.to_csv(processed / "animals.csv", index=False)
    quality_path = reports / "quality.json"
    quality_path.write_text(json.dumps(quality, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    df.loc[~df.analysis_eligible].to_csv(reports / "flagged_rows.csv", index=False)
    treatment_time_summary(df).to_csv(reports / "treatment_by_day.csv", index=False)
    numeric = animals[["n_rows", "n_recorded_days", "n_observed", "n_missing_volume",
                       "n_duplicate_rows", "first_day", "last_day", "followup_days",
                       "observed_followup_days", "min_gap_days", "max_gap_days"]].astype(float)
    description = numeric.describe().T
    description.to_csv(reports / "trajectory_statistics.csv")
    volumes = df.loc[df.analysis_eligible, "tumour_volume"].describe()
    volumes.to_csv(reports / "volume_statistics.csv", header=["volume_mm3"])
    groups = (animals.groupby(["study", "treatment"], observed=True)
              .agg(n_animals=("animal_id", "size"), n_observed=("n_observed", "sum"),
                   median_followup_days=("followup_days", "median"),
                   min_observations=("n_observed", "min"),
                   max_observations=("n_observed", "max")).reset_index())
    groups.to_csv(reports / "treatment_summary.csv", index=False)
    make_figures(df, animals, reports / "figures")
    flags = pd.DataFrame(quality["row_flags"].items(), columns=["Indicateur (lignes)", "Effectif"])
    report = f"""# TumorTwin — Analyse exploratoire (phase 1)

[Glossaire des acronymes](glossary.md) — définitions accessibles hors réseau.

Source : `{source.name}` ; [SHA-256](glossary.md#sha-256) : `{provenance['sha256']}`.
Les colonnes et types lus sont consignés dans `provenance.json`.

{len(df)} lignes, {len(animals)} animaux (clé study + animal_id), {quality['n_studies']} études.
Temps : jours après implantation ; volumes : mm³ (dictionnaire INSPECTumours).
Les jours fournis sont conservés, aucune date calendaire n'est inventée.

## Qualité des données

{_table_markdown(flags)}

{quality['n_irregular_animals']} animaux ont des intervalles enregistrés irréguliers ;
{quality['n_short_histories_lt3']} ont moins de trois mesures exploitables ;
{quality['n_unsorted_animals']} ont des lignes source non triées chronologiquement.
Un historique de trois points n'est pas une garantie d'ajustabilité d'un modèle.

Les lignes brutes, valeurs originales et indicateurs sont conservés dans observations.csv.
Les lignes signalées sont exportées dans flagged_rows.csv. Les statistiques de volume
utilisent exclusivement analysis_eligible : identités, métadonnées, jours et volumes
valides, volumes non négatifs, sans doublon animal-jour ni métadonnées contradictoires.
Les doublons ne sont jamais moyennés. Un volume nul reste une observation valide.
Le suivi enregistré utilise tous les jours valides, même si le volume manque ;
le suivi exploitable est fourni séparément. Les jours négatifs ne sont pas supprimés
automatiquement et doivent être interprétés selon le protocole source.

Sans calendrier des visites prévues, une visite absente ne peut pas être identifiée
comme une valeur manquante. Aucune imputation, interpolation ou régularisation.
Les courbes sont interrompues aux valeurs explicitement manquantes ou exclues ;
les segments entre mesures servent uniquement de guide visuel.

## Statistiques descriptives

{_table_markdown(groups)}

Les statistiques par animal (effectifs, durées, intervalles) sont dans animals.csv ;
les distributions numériques détaillées dans trajectory_statistics.csv et volume_statistics.csv.

![Distributions](figures/distributions.png)

![Intervalles](figures/observation_gaps.png)

![Trajectoires individuelles](figures/individual_trajectories.png)

![Comparaison descriptive des traitements](figures/treatment_comparison.png)

Les comparaisons sont séparées par étude et portent sur les jours réels.
Les barres montrent l'intervalle interquartile, pas un intervalle de confiance.
Les effectifs varient selon la date : l'attrition peut être informative. La distribution
globale des volumes pondère davantage les animaux mesurés plus souvent.
Les étiquettes Drug A/B ne suffisent pas à établir une identité pharmacologique
commune entre études. Aucun effet causal ni aptitude à un usage clinique n'est établi.
Le jeu d'exemple ne garantit pas la représentativité biologique ; les causes des
arrêts de suivi ne sont pas fournies dans ces six colonnes.

## Portée de l'analyse

Aucun modèle n'est entraîné ou évalué. L'[EDA](glossary.md#eda) décrit toutes les données ; elle
ne sert pas à choisir des hyperparamètres sur les individus de test.
"""
    (reports / "phase1_report.md").write_text(report, encoding="utf-8")
    return quality
