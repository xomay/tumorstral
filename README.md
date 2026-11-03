# TumorTwin

Prototype scientifique reproductible combinant, à terme, prévision temporelle
et modélisation mécanistique tumorale. **Les phases 1 et 2 sont implémentées** :
analyse exploratoire et comparaison de quatre modèles individuels de référence.

**Aide à la lecture :** les acronymes du texte sont cliquables.
Consultez le [glossaire des acronymes](src/tumortwin/glossary.md).
Cette convention est inscrite dans AGENTS.md pour les prochaines réalisations.

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
le paquet déclare Python >=3.11. R n'est pas nécessaire : `rdata` lit le [RDA](src/tumortwin/glossary.md#rda).
Les téléchargements nécessitent un accès réseau ([PyPI](src/tumortwin/glossary.md#pypi) et [API](src/tumortwin/glossary.md#api) GitHub) ; après
installation et récupération, analyses et tests fonctionnent hors réseau :

```sh
uv run --offline tumortwin eda --config configs/phase1.toml
uv run --offline pytest
```

Le serveur raw GitHub n'a pas répondu dans l'environnement initial ; le
téléchargeur utilise l'[API](src/tumortwin/glossary.md#api) GitHub Contents. Les restrictions réseau du bac à
sable ont nécessité une autorisation pour les dépendances et les données.

## Utiliser le projet sur un autre appareil

Le dépôt distant est disponible sur [GitHub : xomay/tumortwin](https://github.com/xomay/tumortwin), en accès privé.
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

`download` conserve le [RDA](src/tumortwin/glossary.md#rda), le dictionnaire, la licence Apache 2.0 amont et un
manifeste [SHA-256](src/tumortwin/glossary.md#sha-256) dans `data/raw/`. Il refuse d'écraser un fichier différent de
la révision figée. L'analyse vérifie l'empreinte si ce manifeste est présent.
Les données brutes ne sont pas ajoutées au suivi Git.

Un [CSV](src/tumortwin/glossary.md#csv) local avec ces six noms de colonnes est aussi accepté :

```sh
uv run tumortwin eda --config configs/phase1.toml --input /chemin/example_data.csv
```

Les identifiants [CSV](src/tumortwin/glossary.md#csv) sont lus comme chaînes pour préserver les zéros initiaux.
Les chaînes vides, [NA](src/tumortwin/glossary.md#na), [N/A](src/tumortwin/glossary.md#na), [NaN](src/tumortwin/glossary.md#nan), nan, [NULL](src/tumortwin/glossary.md#null) et null sont interprétées comme
manquantes ; les valeurs originales sont gardées dans les colonnes `raw_*`.
Les espaces périphériques sont retirés des champs normalisés.
Les chemins du [TOML](src/tumortwin/glossary.md#toml) sont relatifs à `project_root`, lui-même relatif au [TOML](src/tumortwin/glossary.md#toml).
Les options [CLI](src/tumortwin/glossary.md#cli) sont relatives au répertoire courant. Les répertoires de sortie
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
src/tumortwin/glossary.md         définitions des acronymes, référence commune
tests/                           tests hors réseau sur données synthétiques
reports/phase1_report.md          rapport généré avec quatre figures
reports/glossary.md               copie du glossaire pour lecture hors réseau
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

Les répertoires baselines et evaluation contiennent la phase 2. Les répertoires
timestral, spatial et coupling restent réservés aux phases suivantes. `notebooks/` est facultatif ;
la [CLI](src/tumortwin/glossary.md#cli) suffit à reproduire toute l'analyse sans état interactif caché.

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
  [NaN](src/tumortwin/glossary.md#nan) n'établit pas la complétude du suivi. Les causes des arrêts ne sont pas connues.
- Comparaisons par étude et jour réel ; [IQR](src/tumortwin/glossary.md#iqr) descriptif, sans test causal.
  Les effectifs changent avec le temps et l'attrition peut être informative.
  Un libellé Drug A/B commun ne prouve pas un même médicament entre études.
- Le jeu d'exemple et ses six colonnes ne documentent pas toute la biologie,
  les protocoles, ni la représentativité d'une population expérimentale.
- La phase 1 n'ajuste aucun modèle. La phase 2 sépare les animaux par
  (study, animal_id), puis ajuste chaque modèle sur le seul passé disponible.
  Ne pas utiliser cette [EDA](src/tumortwin/glossary.md#eda) globale pour régler un modèle sur les futurs animaux de test.
- Aucune donnée [TCIA](src/tumortwin/glossary.md#tcia) n'est téléchargée ; aucun suivi longitudinal [CT](src/tumortwin/glossary.md#ct) n'est supposé.
  Aucune prédiction clinique validée n'est revendiquée.

## Phase 2 — modèles de référence

Le [protocole de phase 2](reports/phase2_plan.md) a été autorisé le 3 novembre 2026.
Voir le [guide d'exécution](reports/phase2_implementation.md).
Le [bilan de validation et les résultats de test](reports/phase2_validation.md)
présentent l'expérience réelle, ses erreurs et ses limites.

Depuis un checkout propre et committé, après `uv sync --locked` et téléchargement :

```sh
uv run tumortwin phase2 split
uv run tumortwin phase2 develop
uv run tumortwin phase2 freeze
uv run tumortwin phase2 evaluate
```

La séparation comprend 104 animaux de développement et 26 de test. Les
prévisions principales utilisent au moins six mesures passées, aux horizons
exacts de 3, 7 et 14 jours. Le critère principal est la [MAE](src/tumortwin/glossary.md#mae)
à sept jours, donnant le même poids à chaque animal. La [RMSE](src/tumortwin/glossary.md#rmse)
et les erreurs relatives complètent le bilan ; seules ces dernières excluent
les cibles nulles. Aucun rééchantillonnage ou volume futur en covariable.
Les résultats du test sont bloqués tant que le développement n'est pas complet
et que la configuration n'a pas été figée sur un commit propre.

Les commandes affichent le répertoire `reports/phase2/<empreinte>/`, contenant
un rapport avec glossaire local, six figures, les prévisions, les cibles exactes,
les scores par animal et les diagnostics de tous les départs du solveur.
Les résultats générés sont ignorés par Git. Chaque changement de code,
configuration, protocole, données ou commit définit une nouvelle expérience.
Les phases terminées sont vérifiées par empreinte avant réutilisation ; une
phase incomplète est conservée pour audit et nécessite un nouveau chemin de
sortie pour recommencer. Aucun écrasement silencieux.

Le projet conserve exactement cinq phases : [EDA](src/tumortwin/glossary.md#eda), baselines, Timestral zero-shot,
réaction-diffusion [3D](src/tumortwin/glossary.md#3d), couplage. **Les phases 3–5 attendent validation.**
L'[API](src/tumortwin/glossary.md#api) Timestral sera vérifiée à la phase 3, sans fine-tuning ni calibration externe.
