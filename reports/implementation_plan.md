# Plan d'implémentation

1. Inspecter Python, les outils et le dépôt ; vérifier le schéma réel de
   `data/example_data.rda` et les effectifs par (study, animal_id).
2. Créer le paquet Python avec uv, téléchargement à révision figée, empreinte
   du fichier brut et adaptateur [RDA](../src/tumortwin/glossary.md#rda)/[CSV](../src/tumortwin/glossary.md#csv) sans imputation.
3. Auditer chaque ligne, calculer les statistiques par individu, traitement et
   étude, préserver les dates et caractériser les intervalles irréguliers.
4. Exporter les données normalisées, tables de qualité, rapport et figures.
5. Tester le schéma, les valeurs manquantes, les doublons, les identités, les
   unités temporelles et le pipeline complet hors réseau ; exécuter sur le jeu réel.

## Phase 2 proposée, non engagée
Le protocole détaillé à valider est dans [phase2_plan.md](phase2_plan.md).
Il précise la séparation 104/26 animaux, les horizons exacts 3/7/14 jours,
les ajustements, la gestion des échecs, les métriques et les critères d'acceptation.

Après validation : figer une séparation par animal (et éventuellement par étude),
définir les origines de prévision et horizons en jours réels, ajuster persistance,
exponentiel, logistique et Gompertz avec SciPy sur les préfixes disponibles.
Comparer [MAE](../src/tumortwin/glossary.md#mae)/[RMSE](../src/tumortwin/glossary.md#rmse) et erreurs relatives uniquement pour les volumes strictement
positifs, sur les mêmes cibles/horizons ; rapporter échecs et identifiabilité.
Choisir les réglages sur les individus d'apprentissage seulement. Aucun modèle
n'est implémenté à ce stade.
