# Organisation des analyses

## Analyse exploratoire

1. Vérifier le schéma réel de `example_data.rda` et les effectifs par (study, animal_id).
2. Charger les données à révision figée avec empreintes et provenance, sans imputation.
3. Auditer les lignes, préserver les jours et caractériser les intervalles irréguliers.
4. Exporter les observations, statistiques descriptives, figures et rapport de qualité.
5. Vérifier le schéma, les valeurs manquantes, les doublons et le pipeline hors réseau.

## Modèles de référence

Le [protocole expérimental](phase2_plan.md) précise la séparation de 104 animaux
de développement et 26 de test, les horizons exacts de 3, 7 et 14 jours, les
ajustements, les métriques et le traitement des échecs.

Les modèles de persistance, exponentiel, logistique et Gompertz sont ajustés
sur les seuls préfixes disponibles. Les comparaisons utilisent les mêmes
cibles, avec une pondération égale par animal. Les paramètres mal identifiés
et les échecs numériques restent visibles dans les exports.

Voir le [guide d'exécution](phase2_implementation.md) et le
[bilan des résultats](phase2_validation.md).
