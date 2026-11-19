# Données

Les fichiers bruts sont immuables et exclus du suivi Git. Les manifestes
enregistrent la source, la révision et l'empreinte
[SHA-256](../src/tumorstral/glossary.md#sha-256). Les datasets conservent leurs
licences respectives, indépendantes de celle du code tumorstral.

## INSPECTumours

`uv run tumorstral download` récupère le jeu public d'exemple INSPECTumours à une
révision figée, son dictionnaire et sa licence. Les empreintes sont dans
`raw/provenance.json`. Conserver la licence amont lors d'un partage des données
ou des tables dérivées. Les fichiers bruts sont ignorés par Git.

`processed/observations.csv` conserve toutes les lignes et les valeurs originales ;
`processed/animals.csv` décrit chaque clé (study, animal_id). Aucun remplacement
des valeurs manquantes et aucune série synthétique dans les résultats expérimentaux.

## Laleh

`uv run --extra timestral tumorstral human download` récupère le supplément
original de Laleh et les poids Timestral épinglés. Les sources sont conservées
sous `raw/laleh/` et `raw/timestral-5m/`, avec leurs manifestes.

Les jours relatifs au traitement et les censures textuelles sont conservés.
Le volume estimé `0.5 * diamètre_mm**3` décrit une lésion cible, pas la charge
tumorale totale. La normalisation sur les trajectoires complètes n'est pas
utilisée. Les identifiants anonymes partagés entre études sont conservés dans
l'audit et exclus des expériences prédictives. Voir le
[protocole humain](../docs/human_protocol.md).
