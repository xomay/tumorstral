# Protocole de prévision préclinique

Ce document décrit le protocole expérimental ; les résultats sont publiés séparément.

## 1. Objectif et limites de l'expérience

Comparer quatre prévisions individuelles de volume : persistance, exponentiel,
logistique et Gompertz. Question principale : à partir du passé observé d'un
animal, quel modèle prévoit le mieux son volume **sept jours plus tard** ?
Les horizons de 3 et 14 jours sont secondaires.

Les modèles sont ajustés séparément sur chaque historique disponible. Ils
n'apprennent pas un effet de traitement partagé entre animaux. La séparation
des animaux sert à développer et figer la procédure numérique sur un ensemble,
puis à évaluer cette procédure sur d'autres animaux. Ajuster les paramètres
sur le préfixe d'un animal de test utilise uniquement ses observations passées.

L'analyse reste préclinique et descriptive. Aucun effet causal, paramètre
biologique démontré ou aptitude clinique ne sont établis. Les six colonnes
ne documentent pas les dates de traitement : impossible de modéliser une
intervention pharmacologique ou d'aligner les courbes sur son administration.

## 2. Données et horizons disponibles

Conserver le [RDA](../src/tumortwin/glossary.md#rda) et sa révision source ; vérifier son [SHA-256](../src/tumortwin/glossary.md#sha-256) et
la provenance du traitement avant chaque exécution. Entrée : observations
avec valeurs originales, jours réels et indicateurs de qualité.
Clé individuelle : `(study, animal_id)` ; unités : mm³ et jours.

Le jeu contient 130 animaux et 1 462 mesures ; tous les historiques sont
irréguliers. 116 animaux ont au moins sept mesures, condition nécessaire
pour disposer de six mesures de contexte et d'au moins une cible future.

Un inventaire des **dates uniquement**, réalisé sans ajustement de modèle,
donne pour les origines ayant au moins six mesures exploitables :

| Horizon exact | Couples origine/cible disponibles | Animaux représentés |
| --- | ---: | ---: |
| 3 jours | 227 | 106 |
| 7 jours | 441 | 91 |
| 14 jours | 229 | 42 |

Ces effectifs couvrent tout le jeu, avant séparation ; ils ne préjugent pas
des effectifs de test ni de la convergence des ajustements. Les couples sont
corrélés lorsqu'ils appartiennent à un même animal. Ne pas les interpréter
comme autant d'expériences indépendantes.

L'[EDA](../src/tumortwin/glossary.md#eda) a déjà porté sur tout le jeu. Le test est un ensemble réservé
aux scores prédictifs après gel du protocole, **pas une évaluation externe
aveugle**. Une confirmation indépendante demanderait d'autres données.

## 3. Séparation des individus et gel du protocole

Répartition : 80 % développement, 20 % test, stratifiés par `(study, treatment)`.
Le traitement ne sert qu'à la stratification et aux analyses descriptives.

| Strate | Animaux | Développement | Test |
| --- | ---: | ---: | ---: |
| Study 1 · Control | 15 | 12 | 3 |
| Study 1 · Drug A | 15 | 12 | 3 |
| Study 1 · Drug B | 10 | 8 | 2 |
| Study 2 · Control | 15 | 12 | 3 |
| Study 2 · Drug A | 15 | 12 | 3 |
| Study 2 · Drug B | 10 | 8 | 2 |
| Study 3 · Control | 30 | 24 | 6 |
| Study 3 · Drug A | 10 | 8 | 2 |
| Study 3 · Drug B | 10 | 8 | 2 |
| **Total** | **130** | **104** | **26** |

Trier les clés de chaque strate par [SHA-256](../src/tumortwin/glossary.md#sha-256) d'une sérialisation [JSON](../src/tumortwin/glossary.md#json) canonique
`[20261103, study, animal_id]`, avec identifiants sous forme de chaînes ; prendre
les premiers 20 % pour le test. Cette règle évite une dépendance au générateur
aléatoire d'une bibliothèque. Les affectations sont exportées dans un
manifeste unique et immuable. Ne jamais rééquilibrer selon volumes, durée du
suivi, existence de cibles ou résultats des modèles.

Sur les 104 animaux de développement : vérifier stabilité numérique, coût et
diagnostics, puis geler la configuration et le commit. Les choix numériques
ci-dessous sont les valeurs du protocole. Toute modification motivée par le
développement sera consignée avant ouverture des scores de test ; tout
changement de question principale, horizon, métrique ou règle de séparation
définit une nouvelle version du protocole, distincte de cette expérience.

Le test est exécuté après ce gel. Aucun réglage n'est modifié pour améliorer
ses résultats. Une répétition corrigée pour bug est explicitement marquée.
Il n'y a pas d'hyperparamètre appris globalement dans ce protocole :
une évaluation croisée n'est donc pas indispensable. Une évaluation laissant
une étude entière de côté serait une expérience complémentaire distincte,
non incluse dans le classement principal.

## 4. Origines et cibles : aucune régularisation du temps

Évaluation principale à origines glissantes et historique croissant :

1. Pour chaque animal, trier les jours source sans modifier les valeurs.
2. À chaque jour observé `t0`, retenir seulement les mesures exploitables
   disponibles à `t <= t0`. Il en faut au moins six, sur six jours distincts.
3. Ajuster chaque modèle sur ce même préfixe, jamais sur la trajectoire complète.
4. Émettre des prévisions à `t0 + 3`, `t0 + 7` et `t0 + 14`, que la cible soit
   disponible ou non. L'[API](../src/tumortwin/glossary.md#api) de prévision ne reçoit aucun volume futur.
5. Scorer uniquement s'il existe une mesure exploitable **exactement** au jour
   demandé. Aucune visite la plus proche, tolérance, interpolation ou extrapolation
   de la cible. Les couples sans cible restent dans le journal avec leur motif.

Le registre des prévisions et celui des cibles sont
distincts ; la jonction pour calculer les erreurs intervient après prévision.
Chaque ligne conserve `t0`, `target_day`, `horizon_days`, taille et durée du
préfixe, lignes source, modèle, paramètres, prévision et statut.

Le rapport de qualité contient un indicateur de conflit de métadonnées calculé
sur toute la trajectoire. Il ne doit pas sélectionner rétrospectivement les
préfixes : reconstruire les contrôles de contexte avec les seules lignes
antérieures à l'origine. Un doublon contemporain reste signalé et inutilisable ;
un conflit de métadonnées dans le préfixe rend ce préfixe inéligible. Le contrôle
de la cible est fait séparément et n'altère pas le préfixe déjà construit.
Tout désaccord futur de métadonnées est journalisé sans devenir une covariable.
Sur le jeu actuel, aucun de ces conflits ou doublons n'a été détecté.

Les [NaN](../src/tumortwin/glossary.md#nan) et observations invalides restent dans les exports ; ils ne sont pas
ajustés ou scorés. Aucune imputation ni élimination automatique des valeurs
extrêmes positives. Les origines sans cible ne prouvent pas une absence de
progression ; les causes d'arrêt du suivi restent inconnues.

Analyse secondaire des historiques courts : utiliser exactement les **3, 4
ou 5 premières mesures exploitables**, une origine par longueur et par animal,
avec les mêmes horizons exacts. Les quatre modèles utilisent les mêmes
préfixes ; rapporter pour chaque longueur les effectifs et échecs. Cette analyse
n'est pas mélangée aux scores principaux et ne sélectionne pas les réglages.
Pour distinguer autant que possible longueur et composition de cohorte, fournir
aussi les comparaisons sur les animaux ayant une cible pour toutes les longueurs
comparées, en signalant qu'il s'agit d'origines calendaires différentes.

## 5. Définition des modèles et ajustement

Poser `tau = t - premier_jour_du_prefixe`, en jours, et `V(tau)` en mm³.
`V0` est le volume initial **ajusté**, non une observation future.

| Modèle | Formule pour tau >= 0 | Paramètres ajustés |
| --- | --- | --- |
| Persistance | `V_hat(t) = dernier_volume_observe` | aucun |
| Exponentiel | `V0 * exp(r * tau)` | `V0`, `r` |
| Logistique | `K / (1 + (K/V0 - 1) * exp(-r*tau))` | `V0`, `r`, `K` |
| Gompertz | `K * exp(log(V0/K) * exp(-r*tau))` | `V0`, `r`, `K` |

`r` s'exprime en jour⁻¹ ; `K` en mm³. Pour l'exponentiel, autoriser un taux
signé afin de représenter croissance et décroissance. Pour logistique et
Gompertz, `r >= 0`, `V0 > 0` et `K > 0` ; permettre `K < V0` représente une
décroissance vers une limite positive. `K` est une asymptote mathématique,
pas une capacité biologique démontrée. Ces modèles autonomes monotones ne
représentent pas une régression suivie d'une reprise, ni les changements de
traitement ; leurs erreurs sur de telles courbes restent visibles.

Ajustement : `scipy.optimize.least_squares`, méthode `trf`, perte
quadratique `linear`, sur les volumes dans leur échelle d'origine. Pour le
conditionnement uniquement, diviser tous les résidus d'un même ajustement par
`s = max(mediane_des_volumes_positifs_du_prefixe, 1 mm³)` ; cela ne change pas
le minimum des carrés. Ne pas transformer les cibles en logarithmes et ne pas
remplacer les zéros par un epsilon.

Paramètres numériques :

- `V0` et `K` entre `1e-6 mm³` et `1000 * max(max_volume_prefixe, 1 mm³)`.
- `r` dans `[-2, 2] jour⁻¹` pour l'exponentiel et `[0, 2] jour⁻¹` pour les
  deux autres modèles. Ces bornes sont des garde-fous numériques, pas des
  connaissances physiologiques ; leur influence est rapportée.
- Initialisations déterministes : `V0` initialisé au premier volume positif
  du préfixe ; exponentiel avec `r` initial dans `{-0.1, 0, 0.1}` ; modèles à
  asymptote avec `r` dans `{0.01, 0.1, 0.5}` et `K` dans
  `{0.5, 1, 2, 10} * max_volume_prefixe`. Projeter les points de départ
  strictement à l'intérieur des bornes. Choisir le départ convergé avec la
  plus petite somme des carrés **sur le préfixe**, égalités départagées par
  l'ordre déclaré ; ne jamais utiliser les erreurs futures.
- Maximum `2000` évaluations par départ ; tolérances `ftol`, `xtol`, `gtol`
  à `1e-8`. Journaliser version SciPy, durée et nombre d'évaluations.

Les zéros restent scorables. Un préfixe entièrement nul donne persistance
nulle et un statut explicite d'ajustement mécanistique non identifiable ;
aucune estimation de `K` ou `r` n'est produite.
Calculer les formules de façon stable, avec détection d'overflow et de valeurs
non finies ; aucune troncature silencieuse d'une prévision très grande mais finie.

La documentation officielle confirme la prise en charge des bornes, pertes et
diagnostics par [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html).
SciPy est géré avec uv et sa version est figée dans uv.lock.

## 6. Convergence, identifiabilité et échecs

Conserver par ajustement : succès du solveur, message, coût, départ retenu,
paramètres, proximité des bornes et valeurs singulières du Jacobien.
Sur un Jacobien adimensionné par les étendues des paramètres, signaler un rang
déficient ou un conditionnement > `1e8`. Déclarer « proche d'une borne » si la
distance relative à celle-ci est < `1e-4`. Ces seuils sont des alertes, pas des
preuves d'identification ou d'incertitude biologique.

Un ajustement convergé mais mal identifié conserve sa prévision finie et un
avertissement ; ne pas le supprimer pour embellir les scores. Un échec est une
absence de convergence pour tous les départs, une impossibilité de calcul,
ou une prévision non finie/négative. Une prévision nulle reste admissible.
Ne pas présenter la covariance locale des paramètres comme une incertitude
prédictive établie.

Le registre conserve tous les échecs. Aucun remplacement silencieux par la
persistance. Les règles d'échec sont gelées avant l'évaluation de test.

## 7. Métriques, comparaison équitable et incertitude

**Critère principal : [MAE](../src/tumortwin/glossary.md#mae) à 7 jours, moyenne par animal puis entre animaux.**
Pour chaque horizon et animal, calculer la moyenne des erreurs absolues sur
ses origines ; puis donner le même poids à chaque animal. Les animaux suivis
plus longtemps ne dominent ainsi pas automatiquement le résultat.

Compléter par :

- [RMSE](../src/tumortwin/glossary.md#rmse) en mm³ : racine de la moyenne entre animaux de leurs [MSE](../src/tumortwin/glossary.md#mse) respectives.
- Erreur signée moyenne, en mm³, pour voir sur/sous-estimation.
- Erreur relative absolue `abs(pred-y)/y`, pour `y > 0` seulement ; rapporter
  médiane et proportion de cibles admissibles. Elle sera secondaire, car de
  petits volumes peuvent produire d'énormes pourcentages. Aucun dénominateur
  artificiel ajouté et aucune exclusion de ces petites cibles des [MAE](../src/tumortwin/glossary.md#mae)/[RMSE](../src/tumortwin/glossary.md#rmse).
- Effectifs d'animaux, origines et cibles ; taux d'échec et alertes numériques,
  par modèle, horizon, étude et traitement. Les petits sous-groupes restent
  descriptifs et ne donnent pas lieu à un classement statistique.

Comparaison principale sur l'intersection **des mêmes couples origine/cible**
avec prévisions valides pour les quatre modèles. Publier sa taille et sa
fraction du registre de couples scorables, ainsi que les performances natives et leur
couverture ; ne pas comparer des moyennes calculées sur des cibles différentes.
Un modèle ne sera pas déclaré gagnant si sa couverture de prévision valide
est <95 %, si le support commun représente <90 % des couples scorables,
ou si moins de 10 animaux sont représentés à l'horizon principal. Dans ce cas,
conclusion explicite : comparaison insuffisamment robuste.

En complément, évaluer sur tous les couples scorables une procédure clairement
nommée « modèle + repli persistance » : les prévisions impossibles sont
remplacées par la dernière observation. Publier fréquence de repli et scores
séparément des modèles natifs. Ce complément évalue une procédure utilisable
sans faire disparaître les cas difficiles.

Comparer les différences de [MAE](../src/tumortwin/glossary.md#mae) à persistance de façon appariée, sur le même
support et avec la même pondération. Un score relatif
`1 - MAE_modele/MAE_persistance` peut être ajouté si le dénominateur est >0.
Un score négatif signifie une dégradation ; une égalité ou un résultat
incertain est un résultat acceptable. Aucune amélioration n'est exigée.

Intervalles exploratoires à 95 % par bootstrap apparié de **2 000 tirages
d'animaux**, en conservant toutes leurs origines ensemble et en stratifiant
par étude, graine `20261103`. Ne pas rééchantillonner les points temporels
comme indépendants. Pas d'intervalle si moins de 10 animaux ; publier alors
les valeurs individuelles. Avec trois études, ces intervalles n'établissent
pas la généralisation à une nouvelle étude. Ne pas transformer les nombreuses
comparaisons secondaires en preuves de supériorité statistique.

Les horizons ont des cohortes différentes ; une différence d'erreur entre
3 et 14 jours ne mesure donc pas seulement la difficulté de l'horizon.
Fournir une analyse secondaire sur les couples `(animal, origine)` possédant
les trois cibles, avec les effectifs restants et le biais vers les suivis longs.

## 8. Code et sorties

| Emplacement | Contenu |
| --- | --- |
| `configs/baselines.toml` | horizons, séparation, bornes, solveur, graines, métriques |
| `src/tumortwin/baselines/` | interface commune, quatre modèles, diagnostics |
| `src/tumortwin/evaluation/` | manifeste d'animaux, origines, scoring et bootstrap |
| `tests/test_baselines.py` | formules, ajustements synthétiques et échecs |
| `tests/test_evaluation.py` | absence de fuite et comparaison équitable |
| `reports/baselines/` | protocole figé, manifeste, prévisions, scores, figures, rapport |

La [CLI](../src/tumortwin/glossary.md#cli) sépare explicitement la création du split,
le développement, le gel et l'évaluation finale : `baselines split`, `baselines develop`,
`baselines freeze` et `baselines evaluate`.
Les sorties sont dans un sous-dossier identifié par empreinte du protocole,
des données et du commit pour éviter de mélanger plusieurs expériences.

Exports minimaux : split, origines (y compris sans cible), ajustements et
diagnostics, prévisions avant jonction des cibles, scores par animal/horizon,
résumés avec couvertures, versions logicielles et configuration finale.
Les sorties générées restent ignorées par Git ; code, protocole et configuration
sont versionnés, sans modifier les fichiers bruts ou les résultats exploratoires.

Figures : scores par horizon avec effectifs ; différences appariées à
persistance ; erreurs selon longueur/durée du contexte ; taux d'échec et
paramètres aux bornes ; exemples de prévision sélectionnés **avant les scores**
par clé d'animal et strate. Montrer aussi les trajectoires mal prévues et les échecs.

## 9. Tests et critères d'acceptation

Tests hors réseau, données synthétiques explicitement identifiées :

1. Formules analytiques, unités, translation de l'origine du temps ; cas
   constants, croissance, décroissance, saturation, zéros et valeurs extrêmes.
2. Récupération de prévisions sur trajectoires synthétiques identifiables,
   et avertissements sur préfixes courts ou presque exponentiels sans plateau.
   Ne pas exiger la récupération unique de paramètres intrinsèquement ambigus.
3. Aucun chevauchement de clé d'animal entre développement et test ; split
   identique après permutation des lignes et identifiants préservés.
4. Modifier les volumes futurs ne change ni ajustement ni prévision d'une origine.
   Ajouter un conflit futur de métadonnées ne change pas son contexte historique.
5. Jours irréguliers conservés ; cible exacte seulement ; absence de cible,
   doublons, [NaN](../src/tumortwin/glossary.md#nan) et erreurs numériques traçables sans suppression silencieuse.
6. Métriques vérifiées sur exemples calculables à la main, pondération par
   animal, support commun identique, dénominateurs nuls et replis explicites.
7. Bootstrap groupé et apparié reproductible ; aucune écriture dans les bruts ;
   pipeline miniature de bout en bout et non-régression des contrôles de données.

Acceptation : tests pertinents réussis, manifestes et provenance vérifiés,
exécution reproductible avec uv, tous les modèles et échecs exportés, tableaux
à horizons identiques, rapport honnête même si persistance gagne. La précision
prédictive n'est pas un critère logiciel d'acceptation.

## 10. Ordre d’exécution

1. Versionner le protocole et figer les dépendances avec uv.
2. Construire le split et le registre temporel ; tester l'absence de fuite.
3. Vérifier les quatre modèles et leurs diagnostics avec les tests hors réseau.
4. Exécuter uniquement le développement ; documenter et geler les réglages.
5. Exécuter le test ; produire scores, couvertures, graphiques et limites.
6. Produire le bilan expérimental.
