# INSPECTumours — extension exploratoire Timestral

Ce protocole étend le [protocole préclinique](preclinical_protocol.md) sans
changer ses quatre modèles, leurs réglages, les origines ou les cibles.
La configuration classique reste utilisable séparément. Cette extension est
définie après consultation des résultats classiques : ce n'est pas une nouvelle
évaluation externe aveugle. Aucun réglage n'est choisi selon les scores du test.

## Individus, dates et comparaison

La clé est `(study, animal_id)`. Même graine `20261103`, même répartition
104 animaux de développement / 26 de test, mêmes origines principales avec au
moins six mesures exploitables, mêmes analyses séparées à trois, quatre et cinq
mesures. Les horizons exacts restent 3, 7 et 14 jours ; le critère principal est
l'[erreur absolue moyenne](../src/tumortwin/glossary.md#mae) à sept jours.
Les jours réels après implantation et les volumes en mm³ sont conservés.
Aucune cible n'est interpolée et aucun volume futur n'entre dans une prévision.

Le support principal est l'intersection des mêmes couples origine/cible avec
prévisions valides pour les cinq modèles. Les supports natifs, la couverture
et le support commun aux quatre références sont aussi exportés. Les seuils
95 % par modèle, 90 % de support commun et dix animaux restent ceux du protocole.
Une sortie négative finie de Timestral reste scorable, avec alerte de domaine ;
une sortie non finie est un échec. Aucun cas n'est supprimé selon son erreur.
Le repli persistance constitue une procédure complémentaire explicitement nommée.

Chaque animal a le même poids après moyenne de ses origines. Les différences
appariées à persistance et à Gompertz utilisent 2 000 tirages d'animaux stratifiés
par étude ; toutes les origines d'un animal restent groupées. Pas d'intervalle
sous dix animaux. Les cohortes diffèrent entre horizons.

## Inférence figée

Timestral-5M est utilisé en [zero-shot](../src/tumortwin/glossary.md#zero-shot),
sans entraînement, fine-tuning, calibration externe ni recherche de réglages.
Code officiel : `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff` ; poids :
`bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`. Les empreintes
[SHA-256](../src/tumortwin/glossary.md#sha-256) des poids locaux sont vérifiées
avant toute inférence ; aucun téléchargement implicite pendant l'évaluation.
Les versions de Timestral et PyTorch entrent dans l'identité de l'expérience.

Le modèle reçoit les volumes originaux du seul préfixe sur une grille quotidienne.
Les jours sans mesure restent absents avec masque, sans imputation par TumorTwin.
Le modèle officiel propage toutefois les valeurs antérieures en interne ; il
conserve le masque et peut compléter les blocs d'entrée avec des zéros masqués.
Cette hypothèse est explicite dans les diagnostics. La symétrisation officielle
est conservée, les plafonds de quantiles et la troncature à zéro sont désactivés.
Les 21 quantiles quotidiens bruts et les sorties négatives sont conservés.

La médiane finie est évaluée même si d'autres quantiles sont invalides. Les scores
probabilistes exigent les 21 quantiles finis et ordonnés ; les échecs et croisements
restent journalisés. Couverture et largeur des intervalles 80 % (10–90 %) et 90 %
(5–95 %), et [pinball loss](../src/tumortwin/glossary.md#pinball-loss), sont
moyennées par animal, séparément pour chaque analyse et horizon. Ces scores
utilisent les cibles exploitables de Timestral, dont l'effectif est publié ; ils
ne dépendent pas de la convergence des références. Aucun intervalle n'est inventé
pour les modèles déterministes.

## Gel, exports et limites

Le cycle développement, gel sur code versionné, puis test est conservé.
Les prévisions sont exportées avant la jonction des volumes futurs. Le dossier
distinct `reports/preclinical_timestral/` préserve les expériences antérieures.
Le protocole figé et son glossaire local sont embarqués dans chaque expérience.

Les intervalles peuvent être larges ou négatifs, donc physiquement inadmissibles.
La rareté du suivi, les changements de cohorte et les traitements non datés
limitent l'interprétation. Le corpus de préentraînement peut contenir des données
publiques apparentées : l'absence de recouvrement avec INSPECTumours n'est pas
démontrée. Aucun effet causal ni usage clinique n'est établi.
