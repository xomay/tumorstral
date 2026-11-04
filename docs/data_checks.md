# Qualité des données INSPECTumours

Cette synthèse décrit le jeu d'exemple INSPECTumours à la révision
`eb41f4f80595b7185cf925a3195d35e1e3b34394`. Les données sont chargées depuis
l'objet `example_data` du fichier [RDA](../src/tumortwin/glossary.md#rda),
avec leurs empreintes et leur dictionnaire source.

## Reproduire les contrôles

Depuis la racine du projet :

```sh
uv sync --locked
uv run tumortwin download
uv run --offline tumortwin eda --config configs/exploration.toml
uv run --offline pytest tests/test_data.py tests/test_eda.py
```

Le téléchargement nécessite le réseau. L'analyse et les tests sont exécutables
hors réseau après installation des dépendances et récupération des données.
Les dépendances sont gérées avec uv.

Les tests couvrent la lecture [CSV](../src/tumortwin/glossary.md#csv) sans perte
des zéros initiaux, la sérialisation et lecture RDA, les schémas invalides et
fichiers vides, les identités multi-études, les jours réels et non triés,
les mesures manquantes, les valeurs non numériques ou infinies, les volumes
négatifs et nuls, les jours négatifs, les doublons animal-jour, les conflits de
métadonnées, les historiques courts et les intervalles irréguliers. Ils
vérifient également la provenance, le refus d'écrasement et la
[CLI](../src/tumortwin/glossary.md#cli) complète avec ses quatre figures.
Les jeux de test sont explicitement synthétiques ; ils ne sont pas inclus
dans les résultats expérimentaux.

## Résultats descriptifs de référence

L'analyse du fichier source donne :

- 1 462 lignes, 130 animaux et 3 études ; 5–28 observations par animal.
- 1 462 lignes exploitables ; aucun doublon animal-jour ou conflit détecté.
- Aucune valeur manquante explicite ni valeur numérique invalide détectée.
- 130 historiques irréguliers, aucun historique de moins de trois mesures.
- Suivi enregistré de 9 à 71 jours ; volumes de 0,523333333 à 3 441 mm³.

Les comparaisons par traitement montrent médianes,
[IQR](../src/tumortwin/glossary.md#iqr) et effectifs aux jours réellement
observés, séparément par étude. Les sorties comprennent un rapport de qualité,
les lignes signalées, les valeurs originales et les statistiques par individu.

## Limites

L'absence de valeur manquante explicite ne permet pas de conclure à un suivi
complet. Les causes des arrêts de suivi ne sont pas documentées. Les analyses
sont descriptives et ne prouvent ni effet causal ni aptitude à un usage clinique.
L'analyse exploratoire ne produit aucun résultat prédictif.
