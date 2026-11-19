# PHS16-LC — intégration Home Assistant

Intégration Home Assistant pour piloter les **luminaires PHS16-LC** (Twin Development sa)
sur leur bus **RS-485 full duplex** : allumer/éteindre, régler l'intensité en mA,
appliquer des **recettes lumineuses** et des **scènes** multi-cartes, sauvegarder en
NVM (`@WP`), superviser les **températures** et la présence des cartes, le tout avec
l'interface web/appli mobile de Home Assistant et son moteur d'automations.

- Cible : **Home Assistant 2026.11+** (Marketplace intégré ; HACS add-on retiré en 2026.11)
- Fonctionne **100 % en local** (pas de cloud) ; l'accès à distance passe par votre VPN.
- Le cœur métier est la copie vendored de [`../phs16ctl/`](../phs16ctl/) (protocole +
  transport + recettes), synchronisée par `tools/sync_phs16ctl.py`.

## Installation

**Manuelle (usage privé, recommandée)** : copier `custom_components/phs16lc/` dans
`/config/custom_components/` de Home Assistant, redémarrer, puis ajouter
l'intégration **PHS16-LC** (Réglages → Appareils et services).

**Marketplace (dépôt privé)** : pousser le contenu de ce dossier `ha-integration/`
à la racine d'un dépôt git privé (avec `hacs.json`), l'ajouter comme dépôt
personnalisé dans Réglages → Marketplace, puis installer « PHS16-LC ».

Au premier ajout, un formulaire demande : le **port série** (liste des ports détectés,
avec détection USB de l'adaptateur FTDI VID `0403` PID `6001`), le **nombre de SPOT
attendus**, l'**intervalle de rafraîchissement** (le protocole ne pousse pas d'état :
les courants/températures sont relus par polling) et le **dossier des recettes**
(`/config/phs16lc/recipes` par défaut — y copier les `recipes/*.json` du projet).

## Entités

Par carte SPOT (device « SPOT n », relié au hub « Adaptateur PHS16-LC ») :
`light` (on/off + luminosité 1–100 % → 74–2150 mA), `select` recette, `select` groupe,
`button` sauvegarder NVM / scènes / scan, `sensor` températures (CPU, LED 1, LED 2) +
courants, `binary_sensor` présence.

Services : `phs16lc.scan`, `phs16lc.apply_recipe`, `phs16lc.apply_scene`,
`phs16lc.save`, `phs16lc.set_channels`, `phs16lc.set_channel`,
`phs16lc.set_group` / `phs16lc.remove_group` (créer/modifier/supprimer un groupe
de luminaires depuis l'UI — Outils de développement → Actions).

## Tableaux de bord et automatisations

- **Blueprints embarqués** dans `custom_components/phs16lc/blueprints/automation/phs16lc/`
  (photopériode de groupe avec mode manuel, recette de groupe, alertes de chambre,
  sauvegarde NVM) : copiés automatiquement au démarrage dans
  `/config/blueprints/automation/phs16lc/`, donc visibles dans Réglages →
  Automatisations → Créer → onglet Blueprint.
- [`dashboards/`](dashboards/) : configuration « Culture » (chambres, sous-groupes,
  plans, recettes, photopériodes). Installable **100 % via l'interface graphique**
  (voir [`dashboards/README.md`](dashboards/README.md) §2) ou générée depuis
  `dashboards/mapping.yaml` via `dashboards/generate_dashboards.py`.

## Développement

Voir [`PLAN.md`](PLAN.md) (plan de développement, décisions figées D1–D18) et
[`GUIDE.md`](GUIDE.md) (matériel, installation, utilisation, dépannage).
Développement/test sur MacBook Pro en local (venv Python 3.14 + `hass -c`), avec ou
sans matériel (`../light-monitor/tools/fake_spot.py`). Tests : `uv run pytest tests/`.
