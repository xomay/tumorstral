# Validation de la phase 1 — 2 novembre 2026

## Environnement et exécution

Python 3.14.4 ; dépendances installées et figées avec uv dans `.venv/`.
Versions utilisées : NumPy 2.5.4, Pandas 3.1.0, Matplotlib 3.11.2,
rdata 1.1.0, pytest 9.2.0. Consulter `uv.lock` et `reports/provenance.json`.

Commandes exécutées depuis la racine du projet :

```sh
export UV_CACHE_DIR="$PWD/.uv-cache"
export MPLCONFIGDIR=/tmp/tumortwin-mpl
.tools/uv sync --cache-dir .uv-cache
.tools/uv run --offline --cache-dir .uv-cache tumortwin download
.tools/uv run --offline --cache-dir .uv-cache tumortwin eda --config configs/phase1.toml
.tools/uv run --offline --cache-dir .uv-cache pytest --junitxml=reports/tests.xml
```

Le drapeau `--offline` concerne la résolution uv ; la commande download utilise
elle-même le réseau. Elle a été exécutée avec accès réseau autorisé. L'analyse
et les tests n'utilisent pas le réseau. Les premières tentatives ont constaté
l'absence de pip/ensurepip et de dépendances ; uv a été téléchargé localement
selon la préférence utilisateur. Aucune installation avec pip.

## Résultats

**24 tests réussis, aucun test ignoré.** Le fichier `tests.xml` enregistre les
résultats JUnit. Les fixtures sont synthétiques ; elles ne figurent pas dans les
tables expérimentales ni dans les résultats du jeu INSPECTumours.

Les tests couvrent : lecture [CSV](../src/tumortwin/glossary.md#csv) sans perte des zéros initiaux, véritable
sérialisation/lecture [RDA](../src/tumortwin/glossary.md#rda), schéma invalide et fichier vide, clé multi-étude,
jours réels et non triés, mesures manquantes, valeurs non numériques/infinies,
volumes négatifs et nuls, jours négatifs conservés, doublons animal-jour,
conflits et absence de métadonnées, absence complète d'identités, historique
court, intervalles irréguliers, contrôle de provenance et refus d'écrasement,
téléchargeur testé sans réseau, [CLI](../src/tumortwin/glossary.md#cli) complète et quatre sorties graphiques.

Le premier passage avait 23 succès et un échec sur le cas sans aucun animal
identifiable : Pandas ne pouvait pas décrire un tableau vide sans colonnes
numériques. Les colonnes numériques sont désormais explicitement définies ;
le cas est inclus dans les 24 tests réussis.

L'analyse réelle a été exécutée sur le [RDA](../src/tumortwin/glossary.md#rda) récupéré, puis relancée après
finalisation du manifeste de provenance. Elle confirme :

- 1 462 lignes, 130 animaux et 3 études ; 5–28 observations par animal.
- 1 462 lignes exploitables ; aucun doublon animal-jour ou conflit détecté.
- Aucune valeur manquante explicite ni valeur numérique invalide détectée.
- 130 historiques irréguliers, aucun historique de moins de trois mesures.
- Suivi enregistré de 9 à 71 jours ; volumes de 0,523333333 à 3 441 mm³.

Les comparaisons par traitement ont été inspectées visuellement : médianes,
[IQR](../src/tumortwin/glossary.md#iqr) et effectifs sont affichés aux jours réellement observés, séparément par étude.

## Limites et périmètre

L'absence de valeur manquante explicite ne permet pas de conclure à un suivi
complet. Les causes des arrêts de suivi ne sont pas documentées. Les analyses
sont descriptives et ne prouvent ni effet causal ni validité clinique.
L'[API](../src/tumortwin/glossary.md#api) GitHub a permis de contourner l'indisponibilité observée du serveur raw.
Aucune dépendance ni aucun dataset nécessaire à la phase 1 ne reste inaccessible.
Les phases 2–5 ne sont pas engagées ; aucun résultat prédictif n'est annoncé.
