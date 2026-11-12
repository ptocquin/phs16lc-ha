# Helpers et blueprints à créer dans l'UI (généré — ne pas éditer)

Conventions : `schedule.photo_<ch>_<groupe>`, `input_boolean.manuel_<ch>_<groupe>`,
`input_select.recette_<ch>_<groupe>`, label `<ch>_<groupe>` sur chaque device SPOT.

## Serre 1 (area `serre_1`)

### Groupe `nord` — SPOT 1, SPOT 2, SPOT 3, SPOT 4

- label `serre_1_nord` à poser sur chaque device SPOT du groupe
- helper **Programme** (schedule) : `schedule.photo_serre_1_nord`
- helper **Booléen** : `input_boolean.manuel_serre_1_nord`
- helper **Liste déroulante** : `input_select.recette_serre_1_nord` (options = noms des fichiers `/config/phs16lc/recipes/*.json`)
- blueprint **Photopériode d'un groupe** : programme=`schedule.photo_serre_1_nord`, cible=`light.serre_1_groupe_nord`, mode manuel=`input_boolean.manuel_serre_1_nord`
- blueprint **Recette d'un groupe** : select=`input_select.recette_serre_1_nord`, groupe=`light.serre_1_groupe_nord`

### Groupe `sud` — SPOT 5, SPOT 6, SPOT 7

- label `serre_1_sud` à poser sur chaque device SPOT du groupe
- helper **Programme** (schedule) : `schedule.photo_serre_1_sud`
- helper **Booléen** : `input_boolean.manuel_serre_1_sud`
- helper **Liste déroulante** : `input_select.recette_serre_1_sud` (options = noms des fichiers `/config/phs16lc/recipes/*.json`)
- blueprint **Photopériode d'un groupe** : programme=`schedule.photo_serre_1_sud`, cible=`light.serre_1_groupe_sud`, mode manuel=`input_boolean.manuel_serre_1_sud`
- blueprint **Recette d'un groupe** : select=`input_select.recette_serre_1_sud`, groupe=`light.serre_1_groupe_sud`

## Serre 2 (area `serre_2`)

### Groupe `all` — SPOT 8, SPOT 9, SPOT 10

- label `serre_2_all` à poser sur chaque device SPOT du groupe
- helper **Programme** (schedule) : `schedule.photo_serre_2_all`
- helper **Booléen** : `input_boolean.manuel_serre_2_all`
- helper **Liste déroulante** : `input_select.recette_serre_2_all` (options = noms des fichiers `/config/phs16lc/recipes/*.json`)
- blueprint **Photopériode d'un groupe** : programme=`schedule.photo_serre_2_all`, cible=`light.serre_2_groupe_all`, mode manuel=`input_boolean.manuel_serre_2_all`
- blueprint **Recette d'un groupe** : select=`input_select.recette_serre_2_all`, groupe=`light.serre_2_groupe_all`
