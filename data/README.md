# Données

`uv run tumortwin download` récupère le jeu public d'exemple INSPECTumours à une
révision figée, son dictionnaire et sa licence. Les empreintes sont dans
`raw/provenance.json`. Conserver la licence amont lors d'un partage des données
ou des tables dérivées. Les fichiers bruts sont ignorés par Git.

`processed/observations.csv` conserve toutes les lignes et les valeurs originales ;
`processed/animals.csv` décrit chaque clé (study, animal_id). Aucun remplacement
des valeurs manquantes et aucune série synthétique dans les résultats expérimentaux.
