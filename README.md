# TumorTwin

Prototype scientifique reproductible combinant, à terme, prévision temporelle
et modélisation mécanistique tumorale. **Seule la phase 1 est implémentée** :
chargement INSPECTumours, contrôle qualité et analyse exploratoire.

## Reproduction avec uv

Depuis la racine du projet, avec [uv](https://docs.astral.sh/uv/) :

```sh
export UV_CACHE_DIR="$PWD/.uv-cache"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
uv sync --locked
uv run tumortwin download
uv run tumortwin eda --config configs/phase1.toml
uv run pytest --junitxml=reports/tests.xml
```

Dans l'environnement de développement utilisé ici, uv est installé localement :
ajouter `export PATH="$PWD/.tools:$PATH"` avant ces commandes. Aucun usage de pip.
`uv.lock` fixe les dépendances et `.python-version` sélectionne Python 3.14 ;
le paquet déclare Python >=3.11. R n'est pas nécessaire : `rdata` lit le RDA.
Les téléchargements nécessitent un accès réseau (PyPI et API GitHub) ; après
installation et récupération, analyses et tests fonctionnent hors réseau :

```sh
uv run --offline tumortwin eda --config configs/phase1.toml
uv run --offline pytest
```

Le serveur raw GitHub n'a pas répondu dans l'environnement initial ; le
téléchargeur utilise l'API GitHub Contents. Les restrictions réseau du bac à
sable ont nécessité une autorisation pour les dépendances et les données.

## Utiliser le projet sur un autre appareil

Le dépôt distant est prévu sous `xomay/tumortwin` sur GitHub, en accès privé.
Avec Git et uv installés et votre compte GitHub authentifié :

```sh
git clone https://github.com/xomay/tumortwin.git
cd tumortwin
uv sync --locked
uv run tumortwin download
uv run tumortwin eda --config configs/phase1.toml
uv run pytest
```

Pour récupérer les changements sur un autre appareil : `git pull --ff-only`.
Pour publier votre travail : créer une branche, committer les modifications,
puis `git push -u origin NOM_DE_BRANCHE`.
L'environnement `.venv`, les caches, les données brutes et traitées, les figures
et rapports générés restent locaux et sont régénérés avec les commandes ci-dessus.
Les fichiers de configuration locaux et secrets sont exclus par `.gitignore`.

## Données et schéma vérifié

Source : [INSPECTumours, AstraZeneca](https://github.com/AstraZeneca/INSPECTumours),
révision `eb41f4f80595b7185cf925a3195d35e1e3b34394`, objet `example_data` du fichier
`data/example_data.rda`. Le [dictionnaire officiel](https://github.com/AstraZeneca/INSPECTumours/blob/eb41f4f80595b7185cf925a3195d35e1e3b34394/man/example_data.Rd)
décrit exactement six colonnes :

| Colonne | Interprétation |
| --- | --- |
| study | Identifiant de l'étude |
| group | Groupe expérimental |
| treatment | Libellé du traitement |
| animal_id | Identifiant animal, combiné avec study |
| day | Jour après implantation, conservé sans réindexation |
| tumour_volume | Volume tumoral en mm³ |

`download` conserve le RDA, le dictionnaire, la licence Apache 2.0 amont et un
manifeste SHA-256 dans `data/raw/`. Il refuse d'écraser un fichier différent de
la révision figée. L'analyse vérifie l'empreinte si ce manifeste est présent.
Les données brutes ne sont pas ajoutées au suivi Git.

Un CSV local avec ces six noms de colonnes est aussi accepté :

```sh
uv run tumortwin eda --config configs/phase1.toml --input /chemin/example_data.csv
```

Les identifiants CSV sont lus comme chaînes pour préserver les zéros initiaux.
Les chaînes vides, NA, N/A, NaN, nan, NULL et null sont interprétées comme
manquantes ; les valeurs originales sont gardées dans les colonnes `raw_*`.
Les espaces périphériques sont retirés des champs normalisés.
Les chemins du TOML sont relatifs à `project_root`, lui-même relatif au TOML.
Les options CLI sont relatives au répertoire courant. Les répertoires de sortie
doivent être distincts du répertoire contenant l'entrée et de ses parents.
Les fichiers produits sont remplacés lors d'une nouvelle analyse.

## Fichiers et sorties

```text
AGENTS.md                         conventions et règles scientifiques
configs/phase1.toml                chemins de l'analyse
data/raw/                         RDA, dictionnaire, licence, provenance
data/processed/observations.csv   toutes les lignes, valeurs brutes et indicateurs
data/processed/animals.csv        effectifs, durées et intervalles par individu
src/tumortwin/data/               téléchargement, lecture et qualité
src/tumortwin/eda.py              tableaux, figures et rapport
src/tumortwin/cli.py              commandes download et eda
tests/                           tests hors réseau sur données synthétiques
reports/phase1_report.md          rapport généré avec quatre figures
reports/quality.json              compteurs de qualité
reports/provenance.json           empreinte, types sources, versions logicielles
reports/flagged_rows.csv          lignes exclues des résumés, sans perte des originaux
reports/trajectory_statistics.csv statistiques des trajectoires
reports/volume_statistics.csv     distribution des volumes exploitables
reports/treatment_summary.csv     résumé par étude et traitement
reports/treatment_by_day.csv      moyenne, médiane, écart-type, IQR et effectifs
reports/figures/                  distributions, intervalles, courbes, comparaisons
reports/implementation_plan.md    plan et proposition de phase 2
reports/validation.md             résultats de validation dans cet environnement
```

Les répertoires baselines, timestral, spatial, coupling et evaluation sont
réservés aux phases suivantes, sans code de modèle. `notebooks/` est facultatif ;
la CLI suffit à reproduire toute l'analyse sans état interactif caché.

## Résultats observés (2 novembre 2026)

L'analyse du fichier réellement téléchargé donne **1 462 lignes, 130 animaux,
3 études**. Chaque animal possède 5 à 28 mesures (médiane 10). Le suivi couvre
9 à 71 jours (médiane 21). Les volumes vont de 0,5233 à 3 441 mm³
(médiane 143,5143 mm³).

Aucune valeur manquante explicite, aucun volume négatif, aucune valeur non
numérique ou infinie, aucun doublon animal-jour ni conflit de métadonnées n'a
été détecté. **Les 130 historiques sont irréguliers** ; les intervalles
enregistrés vont de 2 à 7 jours. Aucun historique n'a moins de trois mesures.
Les tableaux générés restent la source détaillée de ces résultats.

## Hypothèses et limites scientifiques

- Aucune imputation, interpolation, suppression silencieuse ni recalage des jours.
  Toutes les lignes et les valeurs originales sont conservées ; les mesures
  invalides sont signalées et exclues des seuls résumés analytiques.
- Les doublons de jour ou métadonnées contradictoires sont exclus explicitement,
  jamais moyennés. Le seuil « historique court » (<3 mesures) est descriptif.
- Une visite absente est indétectable sans calendrier de visites ; l'absence de
  NaN n'établit pas la complétude du suivi. Les causes des arrêts ne sont pas connues.
- Comparaisons par étude et jour réel ; IQR descriptif, sans test causal.
  Les effectifs changent avec le temps et l'attrition peut être informative.
  Un libellé Drug A/B commun ne prouve pas un même médicament entre études.
- Le jeu d'exemple et ses six colonnes ne documentent pas toute la biologie,
  les protocoles, ni la représentativité d'une population expérimentale.
- Aucun partage apprentissage/test à ce stade : aucun modèle n'est ajusté.
  Une séparation par (study, animal_id) sera obligatoire pour la modélisation.
  Ne pas utiliser cette EDA globale pour régler un modèle sur les futurs animaux de test.
- Aucune donnée TCIA n'est téléchargée ; aucun suivi longitudinal CT n'est supposé.
  Aucune prédiction clinique validée n'est revendiquée.

## Phase 2 proposée — à valider

Figer les individus d'apprentissage et de test avant tout choix de réglage.
Définir des préfixes d'observation et des horizons comparables en jours réels,
puis ajuster avec SciPy persistance, exponentiel, logistique et Gompertz.
Comparer MAE/RMSE et erreurs relatives sur cibles strictement positives,
sur les mêmes couples origine/cible pour tous les modèles. Rapporter les
échecs de convergence et les paramètres mal identifiables ; ne pas réutiliser
les cibles futures comme covariables. Les historiques très courts limitent
l'identifiabilité des modèles logistique et Gompertz.

Le projet conserve exactement cinq phases : EDA, baselines, Timestral zero-shot,
réaction-diffusion 3D, couplage. **Les phases 2–5 attendent validation.**
L'API Timestral sera vérifiée à la phase 3, sans fine-tuning ni calibration externe.
