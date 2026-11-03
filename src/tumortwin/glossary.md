# Glossaire TumorTwin

Les liens placés sur les acronymes conduisent directement à leur définition.
Les unités et formules originales sont conservées. Les définitions des mesures
d'erreur ci-dessous ne constituent pas des résultats de prévision.

## EDA

**Exploratory Data Analysis — analyse exploratoire des données.** Inspection
des distributions, trajectoires et problèmes de qualité avant la modélisation.
Dans TumorTwin, il s'agit de la phase 1.

## MAE

**Mean Absolute Error — erreur absolue moyenne.** Moyenne de `abs(prévision − observation)`.
Elle vaut zéro pour des prévisions exactes ; une valeur plus faible est meilleure.
Pour les volumes, elle s'exprime en mm³. La phase 2 prévoit une moyenne par
animal puis entre animaux pour donner le même poids à chacun.

## MSE

**Mean Squared Error — erreur quadratique moyenne.** Moyenne de
`(prévision − observation)²`, exprimée ici en mm⁶. Elle pénalise davantage
les grandes erreurs. Sa racine carrée redonne une erreur en mm³.

## RMSE

**Root Mean Squared Error — racine de l'erreur quadratique moyenne.**
Racine carrée de la moyenne des erreurs au carré, en mm³ pour les volumes.
Elle est plus sensible aux grandes erreurs que l'erreur absolue moyenne.

## IQR

**Interquartile Range — écart interquartile.** Différence entre le troisième
quartile (75 %) et le premier (25 %). L'intervalle interquartile `[Q25, Q75]`
contient les 50 % centraux des valeurs. Dans les graphiques TumorTwin, les
barres montrent cet intervalle ; elles ne représentent pas un intervalle de confiance.

## API

**Application Programming Interface — interface de programmation.** Ensemble
de fonctions ou points d'accès permettant à un programme d'utiliser un service
ou une bibliothèque, par exemple le téléchargement via GitHub.

## CLI

**Command-Line Interface — interface en ligne de commande.** Manière d'utiliser
un programme depuis un terminal, par exemple `uv run tumortwin eda`.

## CSV

**Comma-Separated Values — valeurs séparées par des virgules.** Format de
tableau texte ; les fichiers TumorTwin utilisent une ligne d'en-têtes.

## JSON

**JavaScript Object Notation.** Format texte structuré utilisé pour les
manifestes de provenance, configurations sérialisées et rapports de qualité.

## TOML

**Tom's Obvious Minimal Language.** Format de configuration texte lisible,
utilisé pour `pyproject.toml` et les fichiers sous `configs/`.

## RDA

**Extension de fichier de données R**, également rencontrée sous la forme
`.RData`. Il s'agit d'un format de sérialisation d'objets R ; le fichier source
INSPECTumours contient l'objet `example_data`.

## SHA-256

**Secure Hash Algorithm, empreinte de 256 bits.** Produit une empreinte d'un
contenu. TumorTwin l'utilise pour détecter une modification de fichier et
identifier précisément les données analysées. Une empreinte n'est pas un chiffrement.

## TCIA

**The Cancer Imaging Archive.** Archive d'imagerie médicale en cancérologie,
source envisagée pour les images et segmentations de la phase 4.

## CT

**Computed Tomography — tomodensitométrie, ou scanner.** Technique d'imagerie
utilisant des rayons X. Un examen isolé ne constitue pas un suivi longitudinal.

## NIfTI

**Neuroimaging Informatics Technology Initiative.** Nom à l'origine du format
d'image volumique `.nii` ou `.nii.gz`, qui stocke notamment une géométrie spatiale.
Le format peut servir à des images et segmentations hors du cerveau.

## MCP

**Model Context Protocol.** Protocole reliant des applications d'IA à des outils
et sources de contexte. Aucun serveur de ce type ne fait partie du projet demandé.

## IA

**Intelligence artificielle.** Terme général pour des méthodes informatiques
réalisant des tâches telles que l'apprentissage de régularités ou la prévision.

## PyPI

**Python Package Index.** Catalogue de paquets Python, interrogé par uv pour
résoudre et télécharger les dépendances du projet.

## NaN

**Not a Number.** Valeur spéciale utilisée notamment pour représenter une donnée
numérique manquante. Elle ne signifie pas que le volume vaut zéro.

## NA

**Not Available**, marqueur de valeur indisponible dans ce projet. Dans les
entrées texte, `NA` et `N/A` sont interprétés comme des valeurs manquantes.
Leur sens exact doit toujours être vérifié dans le dictionnaire de la source.

## NULL

**Marqueur d'absence de valeur**, plutôt qu'acronyme. Les chaînes `NULL` et
`null` sont considérées comme manquantes par le chargeur ; les originaux sont gardés.

## 3D

**Trois dimensions spatiales.** Dans les phases ultérieures, désigne la
représentation spatiale des tissus et de la tumeur, distincte d'une série temporelle.
