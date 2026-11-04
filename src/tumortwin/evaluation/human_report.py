"""Patient-level forecast/truth figures with explicit units and local definitions."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..eda import _table_markdown

PATIENT = ["study", "animal_id"]
PAIR = ["origin_id", "target_day"]
LABELS = {"persistence": "Persistance", "exponential": "Exponentiel",
          "logistic": "Logistique", "gompertz": "Gompertz", "timestral": "Timestral · médiane"}


def _identity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "animal_id" not in result and "patient_id" in result:
        result["animal_id"] = result.patient_id
    for col in PATIENT:
        if col not in result:
            raise ValueError(f"Missing patient identity column: {col}")
        result[col] = result[col].astype("string")
    return result


def _save(fig: plt.Figure, output: Path) -> None:
    fig.tight_layout()
    fig.savefig(output, dpi=140)
    plt.close(fig)


def comparison_support(predictions: pd.DataFrame) -> pd.DataFrame:
    """Return exact common targets, preserving negative finite predictions for diagnostics."""
    required = ["origin_id", "target_day", "model", "prediction", "target_volume", "t0"]
    missing = set(required)-set(predictions)
    if missing:
        raise ValueError(f"Missing forecast columns: {sorted(missing)}")
    df = _identity(predictions)
    if df.duplicated(PAIR+["model"]).any():
        raise ValueError("Duplicate model predictions for an origin and target")
    truths = df.groupby(PAIR).target_volume.nunique(dropna=True)
    if truths.gt(1).any():
        raise ValueError("Different observed truths for the same origin/target")
    if "horizon" not in df:
        df["horizon"] = df.horizon_days if "horizon_days" in df else df.target_day-df.t0
    valid = np.isfinite(df.prediction) & np.isfinite(df.target_volume)
    if "fit_success" in df:
        valid &= df.fit_success.fillna(False).astype(bool)
    if "origin_status" in df:
        valid &= df.origin_status.eq("ok")
    df["report_valid"] = valid
    n_models = df.model.nunique()
    good = df.groupby(PAIR).report_valid.sum()
    good = good.loc[good == n_models].reset_index()[PAIR]
    return df.merge(good, on=PAIR, how="inner", validate="many_to_one")


def _select_examples(predictions: pd.DataFrame, examples: pd.DataFrame | None) -> pd.DataFrame:
    fields = PATIENT+["origin_id", "t0"]
    candidates = predictions[fields].drop_duplicates().sort_values(PATIENT+["t0", "origin_id"])
    if examples is None:
        return candidates.groupby(PATIENT, sort=True).head(1).head(9).reset_index(drop=True)
    examples = _identity(examples)
    keys = PATIENT+(["origin_id"] if "origin_id" in examples else [])
    selected = candidates.merge(examples[keys].drop_duplicates(), on=keys, how="inner")
    return selected.sort_values(PATIENT+["t0", "origin_id"]).groupby(PATIENT, sort=True).head(1).head(9)


def _interval_table(quantiles: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    columns = ["origin_id", "target_day", "horizon", "nominal_coverage", "covered", "width"]
    if quantiles.empty:
        return pd.DataFrame(columns=columns)
    required = set(PAIR+["level", "value"])
    if not required.issubset(quantiles):
        raise ValueError(f"Missing quantile columns: {sorted(required-set(quantiles))}")
    q = quantiles.copy()
    if "model" in q:
        q = q.loc[q.model.str.lower().str.startswith("timestral")]
    if q.duplicated(PAIR+["level"]).any():
        raise ValueError("Duplicate quantile level at an origin and target")
    targets = predictions.loc[predictions.model.str.lower().str.startswith("timestral")]
    if targets.empty:
        return pd.DataFrame(columns=columns)
    targets = targets[PAIR+["target_volume", "horizon"]].drop_duplicates()
    wide = q.pivot(index=PAIR, columns="level", values="value")
    rows = []
    for low, high, nominal in [(.1, .9, .8), (.05, .95, .9)]:
        low_col = next((c for c in wide.columns if np.isclose(float(c), low)), None)
        high_col = next((c for c in wide.columns if np.isclose(float(c), high)), None)
        if low_col is None or high_col is None:
            continue
        intervals = wide[[low_col, high_col]].reset_index().rename(columns={low_col: "low", high_col: "high"})
        intervals = intervals.merge(targets, on=PAIR, validate="one_to_one")
        valid = (np.isfinite(intervals.low) & np.isfinite(intervals.high)
                 & np.isfinite(intervals.target_volume) & intervals.low.le(intervals.high))
        for row in intervals.loc[valid].itertuples(index=False):
            rows.append(dict(origin_id=row.origin_id, target_day=row.target_day, horizon=row.horizon,
                             nominal_coverage=nominal, covered=row.low <= row.target_volume <= row.high,
                             width=row.high-row.low))
    return pd.DataFrame(rows, columns=columns)


def write_human_report(predictions: pd.DataFrame, quantiles: pd.DataFrame,
                       observations: pd.DataFrame, metrics: pd.DataFrame | dict | None,
                       output: Path, metadata: dict,
                       examples: pd.DataFrame | None = None) -> dict[str, Path]:
    """Render supplied held-out forecasts; never fit a model or invent times or units.

    Point columns are study, animal_id (or patient_id), origin_id, t0, target_day,
    model, prediction, target_volume; optional horizon/horizon_days. Quantiles are
    long-form origin_id, target_day, level, value, optionally model. Observations
    use study, animal_id, day, tumour_volume. Metadata must supply volume_label
    and time_label from the audited source. Examples are selected by identity and
    earliest origin, never by observed prediction errors.
    """
    if not metadata.get("volume_label") or not metadata.get("time_label"):
        raise ValueError("Source-specific volume_label and time_label are required")
    df = _identity(predictions)
    common = comparison_support(df)
    if "horizon" not in df:
        df["horizon"] = df.horizon_days if "horizon_days" in df else df.target_day-df.t0
    observed = _identity(observations)
    if not {"day", "tumour_volume"}.issubset(observed):
        raise ValueError("Observations require day and tumour_volume")
    selected = _select_examples(df, examples)
    output = Path(output)
    figures = output/"figures"
    figures.mkdir(parents=True, exist_ok=True)
    (output/"glossary.md").write_text(files("tumortwin").joinpath("glossary.md").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    selected.to_csv(output/"report_examples.csv", index=False)
    time_label, volume_label = metadata["time_label"], metadata["volume_label"]
    models = list(dict.fromkeys(df.model.astype(str)))
    colors = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}
    n = len(selected)
    fig, axes = plt.subplots(max(1, (n+2)//3), min(3, max(1, n)), squeeze=False,
                             figsize=(15, 4*max(1, (n+2)//3)))
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, example in zip(axes.flat, selected.itertuples(index=False)):
        ax.set_visible(True)
        trace = observed.loc[(observed.study == example.study) &
                             (observed.animal_id == example.animal_id)].sort_values("day")
        past, future = trace.loc[trace.day <= example.t0], trace.loc[trace.day > example.t0]
        ax.plot(past.day, past.tumour_volume, "o-", color="black", ms=3, lw=1, label="Passé observé")
        ax.plot(future.day, future.tumour_volume, "o", color="black", mfc="white", ms=4,
                label="Observations futures")
        ax.axvline(example.t0, color="black", ls="--", lw=.8, label="Origine de prévision")
        forecasts = df.loc[df.origin_id == example.origin_id]
        for model in models:
            rows = forecasts.loc[forecasts.model == model].sort_values("target_day")
            ax.plot(rows.target_day, rows.prediction, ".--", ms=4, lw=1,
                    color=colors[model], label=LABELS.get(model, model))
            if not rows.empty and not np.isfinite(rows.prediction).all():
                ax.text(.02, .97-.05*models.index(model), f"{LABELS.get(model, model)} : sortie absente",
                        transform=ax.transAxes, fontsize=7, va="top")
        q = quantiles.loc[quantiles.origin_id == example.origin_id] if not quantiles.empty else quantiles
        if not q.empty:
            if "model" in q:
                q = q.loc[q.model.str.lower().str.startswith("timestral")]
            wide = q.pivot(index="target_day", columns="level", values="value").sort_index()
            for lower, upper, alpha, label in [(.05, .95, .12, "Intervalle prédictif 90 %"),
                                                (.1, .9, .24, "Intervalle prédictif 80 %")]:
                low = next((c for c in wide if np.isclose(float(c), lower)), None)
                high = next((c for c in wide if np.isclose(float(c), upper)), None)
                if low is not None and high is not None:
                    ax.fill_between(wide.index.to_numpy(float), wide[low].to_numpy(float),
                                    wide[high].to_numpy(float), color="#4c78a8", alpha=alpha, label=label)
        ax.set(title=f"{example.study} · patient {example.animal_id}", xlabel=time_label, ylabel=volume_label)
    if n:
        axes.flat[0].legend(fontsize=6, loc="best")
    else:
        axes.flat[0].set_visible(True)
        axes.flat[0].text(.5, .5, "Aucun exemple disponible", ha="center")
    _save(fig, figures/"patient_forecasts.png")

    fig, axes = plt.subplots(1, max(1, len(models)), squeeze=False, figsize=(4*max(1, len(models)), 4))
    for ax, model in zip(axes.flat, models):
        rows = common.loc[common.model == model]
        ax.scatter(rows.target_volume, rows.prediction, s=14, alpha=.6, color=colors[model])
        finite = np.r_[rows.target_volume.to_numpy(float), rows.prediction.to_numpy(float)]
        if len(finite):
            low, high = finite.min(), finite.max()
            if low == high:
                high = low+1
            ax.plot([low, high], [low, high], "k--", lw=.8)
        ax.set(title=f"{LABELS.get(model, model)}\n{len(rows)} couples communs",
               xlabel=f"Observation · {volume_label}", ylabel=f"Prévision · {volume_label}")
    _save(fig, figures/"truth_vs_prediction.png")

    errors = common.copy()
    errors["absolute_error"] = (errors.prediction-errors.target_volume).abs()
    patient_errors = errors.groupby(PATIENT+["model", "horizon"]).absolute_error.mean().reset_index()
    summary = patient_errors.groupby(["model", "horizon"]).agg(
        mean_absolute_error=("absolute_error", "mean"), n_patients=("animal_id", "size")).reset_index()
    summary.to_csv(output/"report_point_scores.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for model in models:
        rows = summary.loc[summary.model == model].sort_values("horizon")
        ax.plot(rows.horizon, rows.mean_absolute_error, "o-", label=LABELS.get(model, model), color=colors[model])
    # Count study + patient, rather than patient identifiers alone.
    patient_counts = common[PATIENT+["horizon"]].drop_duplicates().groupby("horizon").size()
    for horizon, count in patient_counts.items():
        ax.annotate(f"{count} patients", (horizon, .02), xycoords=("data", "axes fraction"),
                    ha="center", fontsize=7)
    ax.set(xlabel=metadata.get("horizon_label", "Horizon dans l'unité temporelle déclarée"),
           ylabel=f"Erreur absolue moyenne par patient · {volume_label}")
    if models:
        ax.legend(fontsize=8)
    _save(fig, figures/"errors_by_horizon.png")

    intervals = _interval_table(quantiles, df)
    intervals.to_csv(output/"report_interval_pairs.csv", index=False)
    interval_summary = intervals.groupby(["horizon", "nominal_coverage"]).agg(
        empirical_coverage=("covered", "mean"), mean_width=("width", "mean"), n_pairs=("covered", "size")).reset_index()
    interval_summary.to_csv(output/"report_interval_scores.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for nominal in [.8, .9]:
        rows = interval_summary.loc[np.isclose(interval_summary.nominal_coverage, nominal)]
        axes[0].plot(rows.horizon, 100*rows.empirical_coverage, "o-", label=f"Intervalle {nominal:.0%}")
        axes[0].axhline(100*nominal, ls="--", alpha=.4)
        axes[1].plot(rows.horizon, rows.mean_width, "o-", label=f"Intervalle {nominal:.0%}")
    axes[0].set(ylabel="Couverture empirique par couple (%)", ylim=(-2, 102),
                xlabel=metadata.get("horizon_label", "Horizon"))
    axes[1].set(ylabel=f"Largeur moyenne par couple · {volume_label}",
                xlabel=metadata.get("horizon_label", "Horizon"))
    if not intervals.empty:
        axes[0].legend(fontsize=8)
        axes[1].legend(fontsize=8)
    else:
        axes[0].text(.5, .5, "Pas d'intervalles évaluables", ha="center", transform=axes[0].transAxes)
    _save(fig, figures/"interval_diagnostics.png")

    coverage_rows = []
    for model, rows in df.groupby("model", sort=True):
        finite = np.isfinite(rows.prediction)
        coverage_rows.append(dict(model=model, n_forecasts=len(rows), finite_forecasts=int(finite.sum()),
                                  negative_forecasts=int((finite & rows.prediction.lt(0)).sum()),
                                  observed_targets=int(np.isfinite(rows.target_volume).sum())))
    support_table = pd.DataFrame(coverage_rows)
    support_table.to_csv(output/"report_support.csv", index=False)
    if isinstance(metrics, pd.DataFrame):
        metrics_text = _table_markdown(metrics.round(6))
    elif isinstance(metrics, dict):
        metrics_text = _table_markdown(pd.DataFrame([(str(k), str(v)) for k, v in metrics.items()],
                                                   columns=["Indicateur", "Valeur"]))
    else:
        metrics_text = "Les scores fournis par le pipeline sont exportés séparément."
    limits = metadata.get("limitations", [])
    if isinstance(limits, str):
        limits = [limits]
    limitations = "\n".join(f"- {text}" for text in limits)
    partition = str(metadata.get("partition", "non précisée"))
    report = f"""# Trajectoires humaines — prévisions et observations

[Glossaire local](glossary.md) · Partition : **{partition}**.

Unité de la mesure : **{volume_label}**. Axe temporel : **{time_label}**.
Ces libellés proviennent des métadonnées de la source ; aucune unité physique
ni date précise n'est reconstruite à partir d'un simple numéro de visite.

## Prévisions individuelles

![Prévisions et observations](figures/patient_forecasts.png)

Les points noirs pleins constituent le passé observé ; les points creux sont
les observations postérieures. Le trait vertical marque l'origine de prévision.
Les bandes montrent les intervalles prédictifs nominaux à 80 % et 90 % de
Timestral, quand ces quantiles sont disponibles. Les segments relient les sorties
du modèle pour la lecture et ne créent aucune mesure entre visites.
Les exemples sont sélectionnés par identité et première origine, sans utiliser
les erreurs ; les identités sont exportées dans report_examples.csv.

## Prévision face à l'observation

![Concordance](figures/truth_vs_prediction.png)

La diagonale représente une prévision égale à la mesure publiée. Les points
au-dessus correspondent à des surestimations. Tous les modèles sont montrés
sur les mêmes couples origine/cible avec une prévision finie. Une prévision
négative reste visible et est comptée dans report_support.csv.

![Erreurs selon l'horizon](figures/errors_by_horizon.png)

L'erreur absolue moyenne ([MAE](glossary.md#mae)) est calculée d'abord par
patient puis entre patients. Les nombres de patients sont indiqués ; les cohortes
peuvent différer entre horizons. Les comparaisons concernent des cibles réellement
mesurées, sans imputation de la vérité.

## Incertitude et support

![Couverture et largeur](figures/interval_diagnostics.png)

Les diagnostics graphiques d'intervalle sont descriptifs par couple, donc sensibles
au nombre d'origines par patient. Les scores probabilistes du pipeline restent
la référence pour les comparaisons pondérées par patient. Une couverture élevée
avec des intervalles très larges ne démontre pas une prévision informative.

{_table_markdown(support_table)}

## Métriques du pipeline

{metrics_text}

## Interprétation

La vérité de comparaison est la mesure publiée, qui comporte son erreur de
mesure et peut être un substitut volumétrique calculé à partir de diamètres.
Une erreur dans des unités normalisées n'est pas une erreur en mm³.
Les résultats portent sur la prévision de la trajectoire observée sous traitement ;
ils n'estiment pas un effet causal de traitement et n'établissent aucune aptitude clinique.

{limitations}
"""
    (output/"report.md").write_text(report, encoding="utf-8")
    return {"report": output/"report.md", "patients": figures/"patient_forecasts.png",
            "scatter": figures/"truth_vs_prediction.png", "errors": figures/"errors_by_horizon.png",
            "intervals": figures/"interval_diagnostics.png"}
