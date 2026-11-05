# Utiliser les modèles de référence précliniques

Le [protocole](preclinical_protocol.md) définit les règles scientifiques ; aucun réglage
ne doit être choisi à partir des scores de test.

## Reproduire une expérience

Installer les dépendances avec `uv sync --locked` et récupérer les données
avec `uv run tumortwin download`. Le dépôt doit être propre et committé pour
figer une expérience. La configuration est `configs/baselines.toml` ; les chemins
sont relatifs à sa racine de projet.

```sh
export UV_CACHE_DIR="$PWD/.uv-cache"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
uv run --offline tumortwin baselines split
uv run --offline tumortwin baselines develop
uv run --offline tumortwin baselines freeze
uv run --offline tumortwin baselines evaluate
```

Quatre processus calculent des origines indépendantes ; la sélection des
départs et l'ordre des exports restent déterministes. Les durées peuvent varier.
Le traitement affiche sa progression sur la sortie d'erreur ; la sortie standard
contient le chemin de l'expérience ou du rapport de partition.

`split` vérifie les empreintes des données brutes, crée une séparation immuable
par animal (104/26 sur le jeu actuel), choisit les exemples et copie protocole,
configuration, glossaire et provenance. La copie du protocole adapte uniquement
les liens du glossaire pour sa lecture locale ; l'empreinte du document source
est conservée dans provenance.json et celle de la copie dans design_manifest.json.
Les strates doivent contenir au moins un animal dans chaque partition ; les
entrées aux identités ou métadonnées ambiguës sont rejetées à cette étape.

`develop` n'ajuste que les animaux de développement. `freeze` exige un
développement complet, des artefacts intacts et un commit propre. `evaluate`
vérifie le gel avant d'ouvrir les cibles de test pour calculer les erreurs.
Chaque origine ajuste ses propres paramètres sur ses observations antérieures.
Les cibles sont persistées et jointes **après** l'export des prévisions.

Le nom d'expérience dépend des empreintes des données, du protocole, de la
configuration, du code, du lock, des versions logicielles et du commit. Une
modification définit une nouvelle expérience ; conserver les dossiers précédents
pour audit. Modifier les bornes ou les départs sur le développement nécessite de
réexécuter ce cycle avec la configuration modifiée, avant les scores de test.

## Lire les sorties

### Ajouter Timestral sans changer l'expérience classique

La configuration `configs/preclinical_timestral.toml` active Timestral et conserve
les mêmes animaux, origines et horizons. Le [protocole de l'extension](preclinical_timestral_protocol.md)
précise son caractère exploratoire, les sorties brutes et le remplissage interne.

```sh
uv sync --locked --extra timestral
uv run --extra timestral tumortwin baselines download-model --config configs/preclinical_timestral.toml
uv run --offline --extra timestral tumortwin baselines split --config configs/preclinical_timestral.toml
uv run --offline --extra timestral tumortwin baselines develop --config configs/preclinical_timestral.toml
uv run --offline --extra timestral tumortwin baselines freeze --config configs/preclinical_timestral.toml
uv run --offline --extra timestral tumortwin baselines evaluate --config configs/preclinical_timestral.toml
```

Les sorties sont dans `reports/preclinical_timestral/<empreinte>/`. Le gel exige
un dépôt propre et versionné après développement. Les poids locaux et le code
installé sont vérifiés avant de calculer l'identité de l'expérience ; l'inférence
ne télécharge aucun fichier. Les fichiers supplémentaires sont :

| Fichier | Contenu |
| --- | --- |
| main_classic_scores.csv | Support commun aux quatre références, conservé séparément |
| main_common_scores.csv | Support commun aux cinq modèles |
| main_common_vs_gompertz_bootstrap.csv | Différences appariées à Gompertz |
| grids.csv | Grilles quotidiennes du passé avec absences et masques |
| quantiles.csv | 21 quantiles bruts aux trois dates demandées |
| daily_quantiles.csv | 21 quantiles bruts pour chacun des quatorze jours futurs |
| timestral_diagnostics.json | Erreurs d'inférence, densité, sorties négatives et quantiles croisés |
| probabilistic_scores.csv | Couverture, largeur et score de quantiles, pondérés par animal |
| pinball_by_level.csv | Score par niveau de quantile |

Les médianes finies négatives restent dans les scores, avec comptage explicite.
Les quantiles invalides n'empêchent pas de scorer une médiane finie ; ils excluent
uniquement les scores probabilistes correspondants. Les distributions négatives
finies et ordonnées restent évaluées et signalées. Les quatre modèles classiques
conservent leurs règles de validité et leurs réglages numériques.

### Sorties communes

Dans `reports/baselines/<empreinte>/` :

| Fichier | Usage |
| --- | --- |
| split.csv | Identités des animaux et partitions, indépendantes des volumes |
| examples.csv | Exemples choisis par identifiant et strate avant scoring |
| provenance.json | Empreintes, commit, versions et configuration |
| design_manifest.json | Empreintes des pièces du plan expérimental |
| freeze.json | Attestation du gel avant test, liée au développement complet |
| glossary.md | Définitions consultables hors réseau |

Dans les sous-dossiers `development/` et `test/` :

| Fichier | Usage |
| --- | --- |
| origins.csv | Contextes, jours réels et lignes source, y compris préfixes inéligibles |
| fits.jsonl | Paramètres, départs, messages, diagnostics numériques et durées |
| predictions.csv | Prévisions sans colonnes de volumes futurs |
| targets.csv | Mesures disponibles à chaque date, sans interpolation |
| scored_registry.csv | Jonction des prévisions et cibles, avec motifs d'absence |
| coverage.csv | Effectifs, couverture, alertes et prévisions sans cible |
| main_common_scores.csv | Comparaison principale sur les mêmes cibles pour quatre modèles |
| main_native_scores.csv | Descriptif des prévisions valides propres à chaque modèle |
| main_fallback_scores.csv | Procédures explicitement assorties du repli persistance |
| main_common_animals.csv | Erreurs par animal, base de la pondération égale |
| main_common_bootstrap.csv | Intervalles exploratoires et différences appariées |
| main_common_horizons_scores.csv | Origines avec cibles aux trois horizons |
| short_3/4/5_* | Analyses séparées des premières mesures et cohortes communes |
| main_subgroups.csv | Comparaisons descriptives par étude et traitement |
| fit_diagnostics.csv | Succès, proximité des bornes, identification fragile, coût numérique |
| report.md et figures/ | Bilan lisible, exemples prédéfinis et diagnostics |
| complete.json | Empreintes des sorties ; une altération bloque leur réutilisation |

Les métriques [MAE](../src/tumortwin/glossary.md#mae) et
[RMSE](../src/tumortwin/glossary.md#rmse) sont en mm³. Le biais positif indique
une surestimation. L'erreur relative est une fraction, uniquement pour les
cibles strictement positives ; sa médiane est calculée par animal puis entre
animaux. Les intervalles appariés donnent la différence à persistance : une
valeur négative indique une diminution de l'erreur sur les mêmes cibles.

Les avertissements de paramètres aux bornes ou de Jacobien mal conditionné
ne retirent pas des scores une prévision finie. Les bornes volumétriques sont
très larges : une proximité relative peut être signalée pour un petit volume
sans proximité absolue biologique. Le conditionnement est calculé après
adimensionnement par les étendues de paramètres. Il sert d'alerte locale et
ne démontre pas la fiabilité de l'incertitude prédictive.

Les zéros ne sont pas imputés. Un historique entièrement nul est non identifiable
pour les trois ajustements mécanistiques ; il reste traité par persistance et
par les procédures de repli explicites. Les calculs numériques impossibles et
prévisions non finies restent des échecs, jamais des suppressions silencieuses.

## Limites et acceptation

Les historiques courts, les petits sous-groupes et les rares suivis longs
limitent l'interprétation. Les modèles monotones ne représentent ni tous les
effets de traitement ni les reprises tumorales. L'analyse exploratoire a déjà
porté sur toutes les données : le test n'est pas une évaluation externe aveugle.

Les modèles natifs sont comparés sur leur support commun. Le rapport vérifie
les seuils de couverture (95 % par modèle et 90 % du support commun), avec
au moins dix animaux à sept jours, comme conditions d'un classement descriptif.
Une amélioration sur la persistance n'est pas un critère d'acceptation logiciel.
Les tests doivent passer, les données rester intactes et tous les échecs être
exportés.
