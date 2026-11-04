# Trajectoires humaines et prévision probabiliste — protocole

## Source et cible

L'expérience utilise le supplément original S1 Data de Laleh et al. (2022),
identifié par [DOI](https://doi.org/10.1371/journal.pcbi.1009822.s006) et empreinte
[SHA-256](../src/tumortwin/glossary.md#sha-256). Les cinq feuilles contiennent les
identifiants anonymes, le jour relatif au traitement, le diamètre de la lésion
cible en millimètres et le bras d'étude. L'original est conservé sans modification.

La cible est `0.5 * diamètre_mm**3`, selon la formule de l'article : un volume
estimé d'une lésion cible en mm³, pas une segmentation anatomique ni la charge
tumorale totale. La normalisation par le maximum global décrite dans l'article
n'est pas utilisée. Toutes les colonnes et coordonnées de lignes restent
disponibles. Les mentions NOT EVALUABLE et TOO SMALL TO MEASURE ne sont pas des
zéros et restent absentes numériquement. Les jours négatifs sont conservés.

Les identifiants source répétés entre plusieurs études ont une indépendance
indémontrée : ces groupes restent dans l'audit et le manifeste, sous la partition
excluded_ambiguous_identity, mais sont exclus des expériences prédictives.
Les libellés de bras restent anonymes ; aucun médicament n'est inventé.

## Séparation et contextes

Séparation déterministe 80/20 par patient, stratifiée par étude et bras sur les
identifiants sans ambiguïté, par tri d'une empreinte de `[20261104, patient_id]`.
Les volumes et durées de suivi n'interviennent pas dans l'affectation.
Les strates sont arrondies vers le bas pour le nombre de patients de test.

Le développement est un pilote de 20 patients sélectionnés par empreinte
d'identité, sans choisir les cas selon les erreurs. Il contrôle l'intégration
numérique ; ses résultats ne sont pas présentés comme ceux de tout le développement.
Le test porte sur tous les patients de la partition de test.

Les origines sont les trois, quatre, cinq et six premières mesures exploitables.
Le contexte de six mesures et la première visite suivante constituent l'analyse
principale. Les contextes plus courts et les deuxième/troisième visites sont
secondaires. Les mesures inexploitables du passé sont conservées dans l'audit,
mais ne comptent pas parmi les mesures du contexte.

Les cibles sont les trois visites datées suivantes, avec leurs jours réels.
Une visite non évaluable reste une cible manquante et n'est pas remplacée par
une visite plus éloignée. Aucun volume cible n'est interpolé. Les demandes de
prévision utilisent uniquement les dates de ces visites ; il s'agit donc d'une
évaluation rétrospective aux dates d'examen observées, pas d'une prévision de
la date du prochain examen. Les délais réels sont exportés pour chaque couple.
Les visites absentes ne sont pas devinées. Les causes d'arrêt restent inconnues.

## Modèles individuels de référence

Persistance, exponentiel, logistique et Gompertz sont ajustés séparément sur
chaque préfixe. Les volumes sont divisés par la médiane positive du seul préfixe
pour le conditionnement, puis les prévisions sont remises à l'échelle originale.
Les jours sont divisés par sept à l'intérieur du solveur ; les dates publiées
restent des jours réels. Les paramètres et leur échelle sont explicitement exportés.
Les bornes, départs multiples et diagnostics restent ceux de la configuration.
Le taux numérique est exprimé par semaine et le volume interne est relatif au
préfixe : les bornes ne sont pas des contraintes physiologiques.

## Timestral-5M zero-shot

Le modèle préentraîné est utilisé sans mise à jour de poids, réglage sur le test,
fine-tuning, covariable future de volume ou recalibration des intervalles.
Le code officiel est figé à `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` ; les poids
à `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`. Le téléchargement garde les
empreintes et licences du code et des poids, qui sont distinctes.

Chaque contexte est placé sur une grille quotidienne. Les jours sans mesure
contiennent [NaN](../src/tumortwin/glossary.md#nan) et un masque d'absence ; ce ne
sont pas nécessairement des visites manquées. TumorTwin n'interpole ni ne remplit
ces positions. **Le code officiel propage toutefois les valeurs antérieures en
interne, tout en conservant le masque** ; cette hypothèse est enregistrée.
Les dates ne sont jamais assimilées aux rangs d'observation. La densité et la
longueur de chaque grille sont exportées. Une date hors grille est signalée.

L'inférence produit les 21 quantiles officiels et la médiane. Les plafonds de
quantiles et la troncature à zéro du forecaster sont explicitement désactivés ;
les sorties négatives restent visibles dans les erreurs et diagnostics.
Les quantiles non finis ou croisés sont signalés et exclus des seuls scores
requérant une distribution cohérente, avec comptage des échecs. La symétrisation
officielle est conservée et documentée. L'environnement uv utilise PyTorch pour
processeur et une option d'installation dédiée, sans imposer ces dépendances
aux seules analyses exploratoires.

## Mesures de performance et graphiques

La comparaison ponctuelle utilise [MAE](../src/tumortwin/glossary.md#mae),
[RMSE](../src/tumortwin/glossary.md#rmse) et biais sur les mêmes couples pour
les cinq modèles. Les erreurs sont moyennées par patient puis entre patients.
Les supports propres à chaque modèle et leur couverture sont publiés séparément.
Les différences à persistance sont accompagnées d'intervalles exploratoires
issus de 2 000 tirages appariés de patients, stratifiés par étude, à partir de
dix patients évaluables. Les très petites cibles ne sont pas retirées des erreurs.

Le critère probabiliste principal est la [pinball loss](../src/tumortwin/glossary.md#pinball-loss),
moyennée sur les 21 niveaux puis par patient, pour la prochaine visite après
six mesures. Les couvertures et largeurs des intervalles à 80 % et 90 % sont
rapportées avec leurs effectifs. Aucun intervalle artificiel n'est attribué
aux baselines. Les quantiles 10 %/90 % délimitent un intervalle à 80 %, pas 90 %.

Les figures comparent observations passées, vérités ultérieures et prévisions,
avec origine et bandes d'incertitude, ainsi que concordance prévision/observation,
erreurs par visite et couverture/largeur des intervalles. Les exemples sont
choisis par identité et strate avant calcul des scores. Le glossaire est local.

Les graines, configurations, source, code, versions et poids définissent une
expérience identifiée par empreinte. Le pilote doit terminer et le dépôt être
propre avant de figer la procédure ; le test est ensuite calculé sans modification
de réglages. Les prévisions sont persistées avant jonction des volumes cibles.
Les prévisions impossibles et les cibles absentes ne disparaissent pas du journal.

## Limites d'interprétation

La source décrit une lésion cible, pas toute la maladie. Les estimations de
volume héritent du bruit des diamètres et d'une hypothèse géométrique. Les
cohortes changent avec la longueur du contexte et l'horizon ; l'attrition peut
être informative. La grille quotidienne est très clairsemée et les modèles
monotones ne capturent pas toutes les réponses aux traitements. L'absence de
recouvrement avec le corpus de préentraînement de Timestral n'est pas démontrée.
Aucun effet causal ni aptitude à une décision clinique n'est établi.
