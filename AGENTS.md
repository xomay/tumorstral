# TumorTwin

## Périmètre
Implémenter uniquement la phase 1. Les phases 2–5 nécessitent une validation
explicite de l'utilisateur. Ne pas ajouter de fine-tuning, calibration externe,
serveur MCP ni interprétation clinique.

## Conventions
Python >=3.11, paquet sous `src/tumortwin`, fonctions typées, chemins pathlib,
CLI reproductible. Utiliser uv, jamais pip. Dépendances figées dans uv.lock.
Les données brutes sont immuables ; conserver leur provenance et SHA-256.
Les tests sont hors réseau et utilisent des fixtures explicitement synthétiques.

## Règles scientifiques
- Clé d'individu : (study, animal_id), jamais animal_id seul.
- Préserver les jours réels après implantation et les volumes en mm³.
- Conserver les valeurs manquantes et les lignes source ; aucune imputation.
- Signaler les doublons, volumes négatifs, valeurs non numériques et historiques
  courts ; ne pas agréger silencieusement les mesures dupliquées.
- Séparer les individus entre apprentissage et test ; aucune cible future
  en covariable. Phase 1 : EDA uniquement, aucune évaluation de modèle.
- Comparaisons de traitements descriptives, sans inférence causale.
- Ne pas inventer de données ni de résultats. Documenter les limites biologiques.
- Les images TCIA ne constituent pas des trajectoires sans suivi démontré.

## Commandes (uv ou .tools/uv dans cet environnement)
`uv sync --locked`
`uv run pytest`
`uv run tumortwin download`
`uv run tumortwin eda --config configs/phase1.toml`
