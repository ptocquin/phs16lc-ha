# Dashboards PHS16-LC — configuration Home Assistant « Culture »

Configuration HA pour piloter les luminaires PHS16-LC organisés en **chambres de
culture** (areas), avec des **sous-groupes de luminaires** par chambre (labels +
light groups), des **recettes** par groupe et des **photopériodes** programmables
(schedules), avec mode manuel.

**Tout est configurable depuis l'interface graphique** (voir §2). Ce dossier ne
contient que des outils optionnels pour ceux qui préfèrent éditer des fichiers :
`mapping.yaml` + `generate_dashboards.py` génèrent en une commande les light groups,
le dashboard et les capteurs d'alerte.

```
dashboards/
├── README.md                  ← ce fichier
├── mapping.yaml               ← TA configuration (optionnel) : chambres, SPOT, groupes, plans
├── generate_dashboards.py     ← générateur (optionnel) : mapping.yaml -> generated/*.yaml
└── generated/                 ← sortie du générateur (ne pas éditer à la main)

custom_components/phs16lc/blueprints/automation/phs16lc/   ← blueprints embarqués dans
    l'intégration : visibles dans Réglages → Automatisations → Créer → onglet « Blueprint »
    ├── photoperiode_groupe.yaml      schedule -> light group (+ mode manuel + resync)
    ├── recette_groupe.yaml           input_select -> apply_recipe sur tout le groupe
    ├── alerte_chambre.yaml           temp max / carte hors ligne -> notification
    ├── save_nvm_apres_recette.yaml   @WP après chaque recette (event phs16lc_recipe_applied)
    └── save_nvm_global.yaml          @WP all à heure fixe (3h par défaut)
```

## 1. Prérequis

- Intégration `phs16lc` installée et fonctionnelle (voir `../README.md`).
- Cartes HACS via le Marketplace (100 % UI) : **auto-entities** (listes par label),
  **mini-graph-card** (courbes de température) ; optionnel **floorplan-card**.
- Images des plans des chambres : soit copiées dans `/config/www/plans/` via l'add-on
  **File editor** (ou Studio Code Server — tous deux en UI web), soit hébergées sur une
  URL externe (`picture-elements` accepte une URL).

## 2. Installation 100 % interface graphique (recommandée)

Aucune édition de fichier YAML requise. Dans l'ordre :

1. **Areas** : Réglages → Appareils et services → onglet Zones → créer une zone par
   chambre (« Serre 1 »…). Ouvrir chaque device « SPOT n » et l'assigner à sa zone.
2. **Labels** : Réglages → Zones, étiquettes… → créer un label par sous-groupe
   (`serre_1_nord`…) ; poser le label sur chaque **device** SPOT du groupe
   (les entités en héritent, ce qui sert aux listes filtrées).
3. **Helpers** (Réglages → Appareils et services → Helpers → « Créer un helper »),
   par sous-groupe `<ch>_<groupe>` :
   - **Groupe → Lampe** : `light.serre_1_groupe_nord` = les `light.spot_n` du groupe ;
     plus un groupe « tous » par chambre (`light.serre_1_tous`).
   - **Programme** (schedule) : `schedule.photo_serre_1_nord` — la photopériode,
     éditable ensuite à tout moment dans l'UI (clic sur l'entité → modifier).
   - **Booléen** : `input_boolean.manuel_serre_1_nord` — ON = contrôle manuel.
   - **Liste déroulante** : `input_select.recette_serre_1_nord` — options = noms des
     fichiers `/config/phs16lc/recipes/*.json`.
   - Par chambre : **Capteur → Min/Max** (type Max) sur les capteurs température des
     SPOT = `sensor.serre_1_temp_max` ; **Groupe → Binary sensor** (type « toutes »)
     sur les `binary_sensor.spot_n_online` = « toutes les cartes en ligne ».
4. **Blueprints** : Réglages → Automatisations et scènes → « Créer une automatisation » →
   onglet **Blueprint** → choisir « PHS16-LC — … » et créer une instance :
   - *Photopériode d'un groupe* par sous-groupe (programme + light group + booléen manuel) ;
   - *Recette d'un groupe* par sous-groupe (input_select + light group) ;
   - *Alertes d'une chambre* par chambre (temp max + groupe binaire + seuil + notif) ;
   - *Save NVM après recette* (1 seule instance, aucun paramètre) ;
   - *Save NVM global* (1 seule instance, heure 3h par défaut).
   > Si les blueprints PHS16-LC n'apparaissent pas dans l'onglet, les copier à la main
   > (une seule fois) : `custom_components/phs16lc/blueprints/automation/phs16lc/*.yaml`
   > → `/config/blueprints/automation/phs16lc/` (via l'add-on File editor).
5. **Dashboard** : Tableaux de bord → « + » → « Culture » (URL `culture`), puis pour
   chaque vue (Vue d'ensemble, Serre 1…5, Programmes, Monitoring) : « Ajouter une vue »,
   type **Sections**, puis « Ajouter une carte » au picker :
   - Vue d'ensemble : cartes **Tuile** par chambre (entité `light.<ch>_tous`, action
     « Naviguer vers » `/culture/<ch>`, fonctionnalité « Luminosité »), tuiles
     température max / cartes en ligne / `line_status` du bus.
   - Vue chambre : carte **Éléments d'image** (`picture-elements`) → choisir l'image
     du plan, puis « + Élément » pour chaque SPOT : icône d'état sur `light.spot_n`
     (positionnée **au clic sur l'image**, tap = « Basculer », hold = « Plus d'infos »),
     badge d'état sur `sensor.spot_n_temp_cpu` et `binary_sensor.spot_n_online` ;
     puis cartes **Tuile** des light groups et **auto-entities** filtrées par label
     (config de la carte en « Éditeur YAML » de la carte, dans l'UI — copier-coller).
   - Programmes : carte **Entités** listant schedules + booléens manuels + input_select
     recettes, et une tuile appelant le service `phs16lc.save` (address `all`).
   - Monitoring : **mini-graph-card** des températures par chambre (YAML de carte),
     ou nativement **Historique** ; **Jauge** sur `sensor.<ch>_temp_max` avec seuils.

## 3. Installation assistée par fichiers (optionnel)

Pour qui édite volontiers du YAML : remplir `mapping.yaml` (chambres → groupes →
adresses SPOT → coordonnées % sur le plan), puis :

```sh
cd ha-integration
uv run python dashboards/generate_dashboards.py
```

Le générateur écrit dans `dashboards/generated/` :

| Fichier | Contenu | À inclure dans `configuration.yaml` |
| --- | --- | --- |
| `groups.yaml` | light groups par sous-groupe + par chambre | `light: !include dashboards/generated/groups.yaml` |
| `templates_alertes.yaml` | `sensor.<ch>_temp_max`, `binary_sensor.<ch>_hors_ligne` | `template: !include …/templates_alertes.yaml` |
| `automations_alertes.yaml` | alertes température / carte HS par chambre | `automation: !include …/automations_alertes.yaml` |
| `scripts.yaml` | `script.phs16lc_save_nvm_all` (@WP all) | `script: !include …/scripts.yaml` |
| `dashboard_culture.yaml` | dashboard Lovelace complet | coller dans un dashboard (mode YAML) |
| `helpers_a_creer.md` | checklist des helpers à créer | — |

> Toute modification du nombre de chambres/SPOT/groupes se fait dans `mapping.yaml`
> puis régénération — ne pas éditer `generated/` à la main.

## 4. Conventions de nommage (utilisées par le générateur et les blueprints)

| Élément | Convention | Exemple |
| --- | --- | --- |
| Area (slug) | clé du mapping | `serre_1` |
| Label par groupe | `<ch>_<groupe>` | `serre_1_nord` |
| Light group | `light.<ch>_groupe_<groupe>` / `light.<ch>_tous` | `light.serre_1_groupe_nord` |
| Schedule | `schedule.photo_<ch>_<groupe>` | `schedule.photo_serre_1_nord` |
| Mode manuel | `input_boolean.manuel_<ch>_<groupe>` | `input_boolean.manuel_serre_1_nord` |
| Recette groupe | `input_select.recette_<ch>_<groupe>` | `input_select.recette_serre_1_nord` |

## 5. Points d'attention

- **Ne pas régler la luminosité d'un light group en usage normal** : `brightness`
  envoie un courant uniforme aux 16 canaux de chaque SPOT et écrase la recette.
  `turn_on` sans luminosité réapplique la dernière recette de chaque SPOT (D11) —
  c'est ce que fait l'automatisation de photopériode.
- **@SP est volatile** : garder actifs les blueprints « Save NVM » (@WP après chaque
  recette + @WP global nocturne). Ne pas les supprimer.
- `phs16lc.apply_recipe`/`save` ne prennent pas de `target:` HA (area/label) : c'est
  pourquoi le blueprint « recette d'un groupe » boucle sur les membres du light group
  via `expand()`.
- Le scan s'arrête au premier silence : garder « nombre de SPOT attendus » renseigné
  dans les options de l'intégration pour détecter une carte HS au milieu du bus.
