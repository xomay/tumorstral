"""Local report and scientific figures; no clinical or causal interpretation."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..baselines import MODELS
from ..data.quality import normalize
from ..eda import _table_markdown

LABELS = dict(persistence="Persistance", exponential="Exponentiel", logistic="Logistique", gompertz="Gompertz")


def save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_report(joined: pd.DataFrame, raw: pd.DataFrame, folder: Path, run: Path,
                 cfg: dict, partition: str) -> None:
    figures = folder/"figures"
    figures.mkdir()
    common = pd.read_csv(folder/"main_common_scores.csv")
    cov = pd.read_csv(folder/"coverage.csv")
    boot = pd.read_csv(folder/"main_common_bootstrap.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for model in MODELS:
        group = common.loc[common.model == model]
        axes[0].plot(group.horizon_days, group.mae, "o-", label=LABELS[model])
        group = cov.loc[(cov.analysis == "main") & (cov.model == model)]
        axes[1].plot(group.horizon_days, 100*group.coverage, "o-", label=LABELS[model])
    axes[0].set(xlabel="Horizon exact (jours)", ylabel="Erreur absolue moyenne par animal (mm³)")
    axes[1].set(xlabel="Horizon exact (jours)", ylabel="Prévisions valides parmi cibles observées (%)", ylim=(-2, 102))
    axes[0].legend(fontsize=8)
    save(fig, figures/"scores_and_coverage.png")
    fig, ax = plt.subplots(figsize=(8, 4))
    for index, model in enumerate(MODELS[1:]):
        group = boot.loc[boot.model == model]
        x = group.horizon_days.to_numpy()+.15*(index-1)
        ax.plot(x, group.delta_mae, "o", label=LABELS[model])
        valid = group.delta_low.notna() & group.delta_high.notna()
        # Intervals are percentile intervals; the point need not lie within them.
        ax.vlines(x[valid], group.loc[valid, "delta_low"], group.loc[valid, "delta_high"])
    ax.axhline(0, color="black", lw=1)
    ax.set(xlabel="Horizon exact (jours)", ylabel="Différence d'erreur absolue à persistance (mm³)")
    ax.legend(fontsize=8)
    save(fig, figures/"paired_differences.png")
    fits = pd.read_json(folder/"fits.jsonl", lines=True)
    diagnostic = fits.groupby(["analysis", "model"]).agg(
        n_fits=("success", "size"), n_success=("success", "sum"),
        n_bound=("near_bound", "sum"), n_condition=("ill_conditioned", "sum"),
        seconds=("elapsed_seconds", "sum"), nfev=("nfev", "sum")).reset_index()
    diagnostic.to_csv(folder/"fit_diagnostics.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 4))
    diagnostic_main = diagnostic.loc[(diagnostic.analysis == "main") & (diagnostic.model != "persistence")]
    x = np.arange(len(diagnostic_main))
    for offset, column, label in [(-.25, "n_success", "Convergence"),
                                  (0, "n_bound", "Proche d'une borne"),
                                  (.25, "n_condition", "Identification fragile")]:
        ax.bar(x+offset, 100*diagnostic_main[column]/diagnostic_main.n_fits, .25, label=label)
    ax.set_xticks(x, [LABELS[m] for m in diagnostic_main.model])
    ax.set(ylabel="Part des ajustements (%)")
    ax.legend(fontsize=8)
    save(fig, figures/"fit_diagnostics.png")
    main = joined.loc[(joined.analysis == "main") & (joined.target_status == "observed")
                      & joined.fit_success & np.isfinite(joined.prediction)].copy()
    main["absolute_error"] = (main.prediction-main.target_volume).abs()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for model in MODELS:
        group = main.loc[main.model == model]
        for ax, column in zip(axes, ["n_context", "context_days"], strict=True):
            ax.scatter(group[column], group.absolute_error, s=8, alpha=.25, label=LABELS[model])
    axes[0].set(xlabel="Nombre de mesures du préfixe", ylabel="Erreur absolue individuelle (mm³)")
    axes[1].set(xlabel="Durée du préfixe (jours)", ylabel="Erreur absolue individuelle (mm³)")
    axes[0].legend(fontsize=8)
    save(fig, figures/"context_errors.png")

    examples = pd.read_csv(run/"examples.csv", dtype={"study": str, "animal_id": str})
    examples = examples.loc[examples.partition == partition]
    normalized = normalize(raw)
    n = len(examples)
    fig, axes = plt.subplots(max(1, (n+2)//3), min(3, max(1, n)), squeeze=False,
                             figsize=(15, 4*max(1, (n+2)//3)))
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, animal in zip(axes.flat, examples.itertuples(index=False)):
        ax.set_visible(True)
        trace = normalized.loc[(normalized.study == animal.study) &
                               (normalized.animal_id == animal.animal_id)].sort_values("day")
        forecasts = joined.loc[(joined.study == animal.study) & (joined.animal_id == animal.animal_id)
                               & (joined.analysis == "main")]
        if not forecasts.empty:
            t0 = forecasts.t0.min()
            ax.axvline(t0, color="black", ls="--", lw=.8)
            for model in MODELS:
                group = forecasts.loc[(forecasts.t0 == t0) & (forecasts.model == model)]
                ax.plot(group.target_day, group.prediction, "o", ms=4, label=LABELS[model])
                if not group.fit_success.all():
                    ax.text(.02, .95-.06*MODELS.index(model), LABELS[model]+" : échec",
                            transform=ax.transAxes, fontsize=7)
        ax.plot(trace.day, trace.tumour_volume.where(trace.analysis_eligible), ".-",
                color="gray", lw=.8, label="Observations")
        ax.set(title=f"{animal.study} · {animal.animal_id} · {animal.treatment}",
               xlabel="Jour après implantation", ylabel="Volume (mm³)")
    if n:
        axes.flat[0].legend(fontsize=7)
    save(fig, figures/"preselected_examples.png")

    primary = common.loc[common.horizon_days == cfg["primary_horizon"]]
    primary_cov = cov.loc[(cov.analysis == "main") & (cov.horizon_days == cfg["primary_horizon"])]
    denominators = primary_cov.n_scorable
    total = int(denominators.iloc[0]) if len(denominators) else 0
    common_count = int(primary.n_pairs.iloc[0]) if len(primary) else 0
    fraction = common_count/total if total else 0.
    n_animals = int(primary.n_animals.iloc[0]) if len(primary) else 0
    eligible = (n_animals >= cfg["bootstrap_min_animals"] and fraction >= cfg["min_common_coverage"]
                and len(primary_cov) == 4 and primary_cov.coverage.ge(cfg["min_model_coverage"]).all())
    conclusion = ("Les seuils de couverture et d'effectif sont satisfaits ; comparer les différences "
                  "appariées et leurs intervalles exploratoires avant toute affirmation de supériorité."
                  if eligible else "Comparaison insuffisamment robuste pour déclarer un gagnant selon "
                  "les seuils prévus au protocole.")
    summary = dict(partition=partition, primary_horizon=cfg["primary_horizon"],
                   n_scorable_pairs=total, common_support_pairs=common_count,
                   common_support_fraction=fraction, n_primary_animals=n_animals,
                   ranking_coverage_eligible=bool(eligible), conclusion=conclusion)
    (folder/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    table = common.rename(columns={"horizon_days": "Horizon (jours)", "model": "Modèle",
                                   "n_animals": "Animaux", "n_pairs": "Couples",
                                   "mae": "Erreur absolue (mm³)", "rmse": "Erreur quadratique (mm³)"})
    table = table[["Horizon (jours)", "Modèle", "Animaux", "Couples",
                   "Erreur absolue (mm³)", "Erreur quadratique (mm³)"]].round(3)
    relative_glossary = "../glossary.md"
    report = f"""# TumorTwin — Phase 2 : {partition}

[Glossaire local]({relative_glossary}) · [Protocole figé](../protocol.md) · [Provenance](../provenance.json)

## Résultat principal

{conclusion}

À 7 jours : {total} couples origine/cible scorables ; {common_count} sur le support
commun ({fraction:.1%}), représentant {n_animals} animaux. La couverture individuelle
est dans coverage.csv. Les mêmes couples sont utilisés pour les quatre modèles.

{_table_markdown(table)}

L'erreur absolue moyenne ([MAE]({relative_glossary}#mae)) donne le même poids à chaque
animal, après moyenne sur ses origines. La racine de l'erreur quadratique moyenne
([RMSE]({relative_glossary}#rmse)) applique la même pondération aux carrés des erreurs.
Les tableaux native_scores décrivent les seules prévisions valides de chaque modèle,
avec des supports potentiellement différents : ils ne servent pas à classer les modèles.
Les tableaux fallback_scores décrivent explicitement le modèle avec repli persistance
en cas d'échec ; sa fréquence est indiquée. Aucun échec ne disparaît du registre.

![Scores et couverture](figures/scores_and_coverage.png)

![Différences appariées](figures/paired_differences.png)

Les intervalles des différences proviennent de tirages d'animaux appariés et
stratifiés par étude. Ils sont exploratoires, absents sous dix animaux, et
ne prouvent pas une généralisation à une nouvelle étude. Une différence négative
signifie une erreur inférieure à persistance sur le même support.

## Diagnostics et sensibilités

![Diagnostics](figures/fit_diagnostics.png)

Les bornes sont numériques. Une asymptote ou un taux mal identifié n'est pas
un paramètre biologique validé. Les avertissements ne retirent pas les prévisions
finies des scores. Les paramètres, valeurs singulières, coûts et tous les départs
du solveur sont conservés dans fits.jsonl.

![Erreurs et historique](figures/context_errors.png)

Les nuages représentent des erreurs individuelles corrélées, pas des observations
indépendantes. Les analyses short_3, short_4 et short_5 utilisent seulement les
trois, quatre ou cinq premières mesures, séparément des résultats principaux.
Les tableaux matched restreignent aux animaux avec cibles pour les trois longueurs.
Les tableaux common_horizons restreignent aux origines ayant les trois horizons.
Une table vide signifie qu'aucun cas ne satisfait cette intersection.

## Exemples choisis avant les erreurs

![Exemples](figures/preselected_examples.png)

Les animaux viennent de examples.csv, choisi par identifiant et strate avant les
scores. Le trait vertical marque la première origine principale disponible ;
les points colorés sont les prévisions à 3, 7 et 14 jours. Les observations
postérieures sont affichées pour comparaison, sans entrer dans cet ajustement.
Les échecs des exemples sont indiqués ; tous les autres sont dans les exports.

## Limites

Jours réels conservés, cibles exactes seulement, aucune interpolation ni imputation.
Les suivis interrompus n'ont pas de cible extrapolée ; l'attrition peut être
informative, notamment à 14 jours. Les cohortes diffèrent entre horizons.
Les comparaisons par étude/traitement sont descriptives et les petits groupes
fragiles. Les volumes proches de zéro rendent les erreurs relatives instables ;
elles sont secondaires et ne sont calculées que pour les cibles strictement positives.
Les pourcentages sont des fractions dans les exports (multiplier par 100 pour les lire).
Les modèles monotones ne représentent pas toutes les réponses ou reprises sous traitement.
L'analyse exploratoire de phase 1 a déjà vu tout le jeu : ce test n'est pas une
validation externe aveugle. Aucun effet causal ou usage clinique n'est démontré.
La phase 3 n'est pas engagée.
"""
    (folder/"report.md").write_text(report, encoding="utf-8")
