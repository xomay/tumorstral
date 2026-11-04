# TumorTwin

## Périmètre
Le projet couvre l'analyse exploratoire, les modèles individuels de référence
et les prévisions zero-shot Timestral sur les données humaines Laleh.
Suivre le protocole `reports/phase2_plan.md`. Ne pas ajouter de fine-tuning, calibration externe,
serveur [MCP](src/tumortwin/glossary.md#mcp) ni interprétation clinique.

## Conventions
Python >=3.11, paquet sous `src/tumortwin`, fonctions typées, chemins pathlib,
[CLI](src/tumortwin/glossary.md#cli) reproductible. Utiliser uv, jamais pip. Dépendances figées dans uv.lock.
Les données brutes sont immuables ; conserver leur provenance et [SHA-256](src/tumortwin/glossary.md#sha-256).
Les tests sont hors réseau et utilisent des fixtures explicitement synthétiques.

## Accessibilité des acronymes — convention permanente
Pour toute prochaine réalisation dans ce projet (documentation, rapport généré,
graphique ou interface), rendre les acronymes compréhensibles sans recherche externe.
Le glossaire de référence est [src/tumortwin/glossary.md](src/tumortwin/glossary.md).

- Relier les acronymes du texte à leur définition par des liens Markdown directs.
- Ajouter une définition au glossaire avant d'introduire un nouvel acronyme.
- Dans les graphiques, développer le terme dans le libellé ou la légende.
- Dans les interfaces, proposer une aide accessible au clavier et au clic ;
  une infobulle au survol seule ne suffit pas.
- Les rapports exportés doivent embarquer un glossaire local accessible hors réseau.
- Préserver les noms techniques, commandes, chemins et formules dans les blocs de code.

## Règles scientifiques
- Clé d'individu : (study, animal_id), jamais animal_id seul.
- Préserver les jours réels après implantation et les volumes en mm³.
- Pour Laleh : jours relatifs au traitement et volumes estimés par 0,5 × diamètre³,
  sans normalisation globale. Préserver les censures textuelles ; ne pas les coder zéro.
- Exclure des expériences prédictives les identifiants anonymes réutilisés entre études.
- Timestral : poids figés, aucun fine-tuning, grille quotidienne masquée ; documenter
  le remplissage interne du modèle et conserver les sorties négatives brutes.
- Conserver les valeurs manquantes et les lignes source ; aucune imputation.
- Signaler les doublons, volumes négatifs, valeurs non numériques et historiques
  courts ; ne pas agréger silencieusement les mesures dupliquées.
- Séparer les individus entre apprentissage et test ; aucune cible future
  en covariable. Reconstruire les contrôles de chaque préfixe sans données futures.
- Comparaisons de traitements descriptives, sans inférence causale.
- Ne pas inventer de données ni de résultats. Documenter les limites biologiques.
- Les images [TCIA](src/tumortwin/glossary.md#tcia) ne constituent pas des trajectoires sans suivi démontré.

## Commandes (uv ou .tools/uv dans cet environnement)
`uv sync --locked`
`uv run pytest`
`uv run tumortwin download`
`uv run tumortwin eda --config configs/phase1.toml`
`uv run tumortwin phase2 split`
`uv run tumortwin phase2 develop`
`uv run tumortwin phase2 freeze`
`uv run tumortwin phase2 evaluate`
