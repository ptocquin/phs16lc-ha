# PLAN de développement — intégration Home Assistant `phs16lc`

Plan de l'intégration Home Assistant qui expose les luminaires PHS16-LC
(pilotés par `phs16ctl/`) dans l'interface Home Assistant, pour un contrôle
local et à distance (via le VPN de l'entreprise).

> **Document vivant** — mis à jour au fur et à mesure du développement.
> Version : 0.5 — 2026-11-11 — phase 2 réalisée (entité light, 25 tests OK).
> Version : 0.4 — 2026-11-11 — phase 1 réalisée (coordinator + présence, 17 tests OK).
> Version : 0.3 — 2026-11-11 — phase 0 réalisée (squelette + vendored phs16ctl + tests OK).
> Version : 0.2 — 2026-11-11 — ajout de la boucle de développement/test sur
> MacBook Pro (macOS 26.6) et de la procédure de déploiement sur PC Linux.
> Version : 0.1 — 2026-11-11 — état : cadrage figé, développement non commencé.
> Voir [`GUIDE.md`](GUIDE.md) pour le matériel, l'installation et l'utilisation.
> Le protocole et la logique métier restent documentés dans [`../README.md`](../README.md)
> et [`../phs16ctl/`](../phs16ctl/).

---

## 1. Objectifs

1. Piloter chaque luminaire PHS16-LC depuis l'interface Home Assistant (web +
   appli mobile) : on/off, intensité, recettes lumineuses, scènes multi-cartes,
   sauvegarde NVM.
2. Superviser : températures (CPU, cartes LED 1/2), présence des cartes,
   courants appliqués — avec historique consultable dans HA.
3. Permettre des **automations** HA (photopériode, alertes de température…)
   qui se nourrissent aussi de sondes externes ajoutées plus tard.
4. **Ne rien réinventer** : réutiliser `phs16ctl` (protocol + link + controller)
   tel quel comme cœur métier ; n'écrire que l'enveloppe « entités HA ».
5. Rester **local-first** : tout fonctionne sans Internet ; l'accès à distance
   passe par le VPN entreprise existant (aucun port ouvert, pas de cloud).

## 2. Décisions figées

| # | Choix | Décision | Pourquoi |
| --- | --- | --- | --- |
| D1 | Plateforme | **Home Assistant 2026.11.x** (cible de référence) | L'utilisateur la connaît ; UI web + appli + automations + historique intégrés. Depuis la **2026.11** (04/11/2026), HACS est retiré et remplacé par le **Marketplace** intégré (Réglages → Marketplace) — plus rien à installer séparément. |
| D2 | Type d'installation HA | **Home Assistant OS** recommandé (Raspberry Pi 5 + SSD, ou mini-PC x86) ; HA Container accepté | HA OS = le plus plug-and-play (màj, add-ons, sauvegardes). Voir GUIDE §4. |
| D3 | Forme de l'intégration | Intégration custom **`phs16lc`** dans `custom_components/phs16lc/`, `integration_type: "hub"` | Un hub = le lien série ; un *device* par carte SPOT. |
| D4 | Distribution du code | Par défaut : **copie manuelle privée** dans `/config/custom_components/`. Option : dépôt git privé + `hacs.json` → installable/màj via le Marketplace | Usage privé : zéro infrastructure. Le Marketplace n'audite rien : on ne publie pas publiquement. |
| D5 | Cœur métier | `phs16ctl` **vendored** (copié) dans l'intégration, synchronisé depuis `../phs16ctl/src/phs16ctl/` par un script | Source de vérité unique = `phs16ctl/`. Pas de dépendance réseau à l'installation (pas sur PyPI). `protocol.py`, `link.py`, `controller.py` restent inchangés. |
| D6 | Accès au port série | `pyserial` déclaré dans `manifest.json` (`requirements`), épinglé à la **même version que `package_constraints.txt` de HA core** (hassfest vérifie la compatibilité) | `pyserial` est déjà présent dans l'environnement HA (intégration core `serial`). |
| D7 | Unicité du port | **Un seul propriétaire de `/dev/ttyUSB0`** : l'intégration HA. La CLI `phs16ctl` ne doit pas tourner en même temps sur le même port | Un port série ne s'ouvre qu'une fois. Documenté dans le GUIDE. |
| D8 | I/O série dans HA | Tout appel bloquant (`PhsLink.send`) exécuté via **`hass.async_add_executor_job`** | pyserial est bloquant ; jamais dans la boucle événementielle. |
| D9 | Configuration | **Config flow** (UI) : port série (liste détectée + saisie manuelle), nombre de SPOT attendus, intervalle de polling, dossier des recettes. **Options flow** pour modifier sans recréer | Depuis 2026.11, le config flow s'ouvre sans redémarrage depuis le Marketplace. |
| D10 | Mapping luminosité | HA brightness 1–255 → **74–2150 mA linéaire** (`mA = 74 + (2150-74)·b/255`) ; 0 = éteint. État « on » = au moins un canal ≥ 74 mA ; luminosité affichée = courant max des canaux | Mappe le curseur HA directement sur la plage réelle des drivers. |
| D11 | `turn_on` sans luminosité | Réapplique la **dernière recette** appliquée à la carte si elle existe, sinon 500 mA (`DEFAULT_CURRENT_MA`) | Évite une mauvaise surprise après une recette. |
| D12 | Polling | `DataUpdateCoordinator`, intervalle **10 s par défaut** (options : 5–60 s). Scan `@GI` au démarrage + à la demande (bouton/service) | Le protocole est maître/esclave : pas de push, l'état réel se lit par `@GP`/`@GT`. |
| D13 | Historique | `recorder` HA (sensors + états de lights) + **événements HA** (`phs16lc_recipe_applied`, `phs16lc_scene_applied`, `phs16lc_saved`) visibles dans le *logbook* | Historique natif HA, sans code custom. Le `history.csv` de la CLI reste pour l'usage CLI. |
| D14 | Accès distant | **VPN entreprise existant** ; appli mobile HA via le VPN. Pas de Nabu Casa, pas de port ouvert, pas de tunnel cloud | La machine est sur le réseau de l'entreprise, déjà joignable par VPN. |
| D15 | Langues | `translations/` en **fr** et **en** (config flow, entités, services) | Projet francophone. |
| D16 | Cible de test | `pytest-homeassistant` (package central officiel, épinglé à HA 2026.11.x — l'ancien `pytest-homeassistant-custom-component` est abandonné en 2026) + `FakeLink` (tests unitaires) + `fake_spot.py` (pty) pour le end-to-end sans matériel | Même philosophie que `phs16ctl` : testable sans matériel. |
| D17 | Environnement de développement | **MacBook Pro (macOS 26.6, Apple Silicon)** : backend via `uv` (Python 3.14.9 — HA 2026.11 exige Python ≥ 3.14.2 **et** un venv, contrôle `validate_environment()` au boot) ; HA local via `hass -c <config>` en venv, accès direct au port série ; port `/dev/cu.usbserial-XXXX` après installation du pilote FTDI VCP + validation de l'extension système | Sur Mac, Docker ne passe pas fiablement l'USB série dans le conteneur ; le venv donne un accès direct au `/dev/cu.*` et un code live via symlink. macOS = développement uniquement, jamais de production. |
| D18 | Déploiement sur le PC Linux | **Aucun changement de code** : même dossier `custom_components/phs16lc/` copié dans `/config/custom_components/` ; seul le port change (`/dev/cu.usbserial-XXXX` → `/dev/ttyUSB0`), reconfiguré dans le config flow — la détection USB par VID/PID `0403:6001` est identique des deux côtés | L'intégration est en pur Python + pyserial, portable macOS/Linux ; le port est une donnée de configuration, pas du code. |

## 3. Architecture

```
Internet ──VPN entreprise──► ┌──────────────── Home Assistant (mini-PC dédié) ────────────────┐
                              │  Intégration custom `phs16lc` (custom_components/phs16lc/)      │
                              │  ├── config_flow / options flow                               │
                              │  ├── coordinator (polling @GI/@GP/@GT toutes les 10 s)        │
                              │  ├── entités : light / select / button / sensor / binary_sensor│
                              │  ├── services : scan, apply_recipe, apply_scene, save, …       │
                              │  └── phs16ctl vendored (protocol.py, link.py, controller.py)   │
                              │         │ pyserial (executor)                                 │
                              │         ▼ /dev/ttyUSB0                                        │
                              │  Adaptateur FTDI USB-RS422-WE (full duplex 4 fils)            │
                              └─────────┼────────────── bus RS-485 RJ45 ──────────────────────┘
                                        ▼
                              SPOT 1 ── SPOT 2 ── … ── SPOT N   (PHS16-LC, adresses 1..N)
```

Arborescence prévue dans ce dossier :

```
ha-integration/
├── PLAN.md                  ← ce fichier (cadrage + suivi)
├── GUIDE.md                 ← matériel, installation, utilisation
├── README.md                ← présentation de l'intégration (Marketplace)
├── hacs.json                ← métadonnées Marketplace (homeassistant: "2026.11.0")
├── custom_components/phs16lc/
│   ├── manifest.json        ← domain, name, version, integration_type, categories,
│   │                          usb (0403:6001), requirements [pyserial==<pin core>]
│   ├── __init__.py          ← setup entry, coordinator, registre devices
│   ├── config_flow.py       ← port, expected_spots, poll_interval, recipes_dir
│   ├── const.py             ← constantes, événements, mapping mA↔brightness
│   ├── coordinator.py       ← PhsLink + polling (executor)
│   ├── light.py             ← 1 light par SPOT
│   ├── select.py            ← recette + groupe par SPOT
│   ├── button.py            ← save NVM, scènes, scan
│   ├── sensor.py            ← températures, courants, état
│   ├── binary_sensor.py     ← présence par SPOT
│   ├── services.yaml        ← services exposés
│   ├── diagnostics.py       ← dump @GL, ports, etc.
│   ├── phs16ctl/            ← copie vendored de ../phs16ctl/src/phs16ctl/
│   └── translations/        ← fr.json, en.json
├── brand/                   ← icon.png, logo.png (requis Marketplace)
├── tools/
│   └── sync_phs16ctl.py     ← recopie ../phs16ctl/src/phs16ctl → custom_components/phs16lc/phs16ctl
└── tests/                   ← tests unitaires (FakeLink) + e2e (fake_spot pty)
```

### 3.1 Boucle de développement sur MacBook Pro (cette machine)

Tout le développement et les tests se font sur le MacBook Pro (macOS 26.6.2,
Apple Silicon), y compris avec les **vrais luminaires branchés en USB**. Le
déploiement final vise un PC Linux (voir D18 et phase 9) : aucun changement de
code n'y est nécessaire.

**Prérequis Mac** :

- `uv` (déjà installé sur cette machine) fournit Python 3.14.9. HA 2026.11
  exige Python ≥ 3.14.2 **et** un venv — le `python3` système (3.9) ne convient pas.
- Pilote **FTDI VCP** à installer depuis <https://ftdichip.com/drivers/vcp-drivers/>
  (macOS ≥ 26.6 ne l'inclut plus), puis extension à valider dans *Réglages
  Système → Confidentialité et sécurité*, redémarrer. Le câble USB-RS422-WE
  apparaît alors en `/dev/cu.usbserial-XXXX` (préfixe `cu.`, pas `tty.`).
  Voir `../README.md` §7.2.

**Tester le backend `phs16ctl` seul (sans HA)** :

```sh
cd phs16ctl
uv sync
uv run pytest                                       # tests FakeLink, sans matériel
uv run phs16ctl --list-ports                        # doit lister /dev/cu.usbserial-XXXX
uv run phs16ctl --port /dev/cu.usbserial-XXXX scan  # vrais luminaires branchés
# Sans luminaire : simulateur sur port pty
python3 ../light-monitor/tools/fake_spot.py --boards 3 > /tmp/port.txt 2>/tmp/trames.log &
sleep 1
uv run phs16ctl --port "$(cat /tmp/port.txt)" scan
```

**Tests unitaires de l'intégration HA** (fixtures HA + FakeLink, aucune I/O réelle) :

```sh
cd ha-integration
uv venv --python 3.14 .venv
uv pip install -p .venv "homeassistant==2026.11.*" "pytest-homeassistant==2026.11.*" pytest pyserial
uv run --python .venv/bin/python pytest tests/ -v
```

**Faire tourner Home Assistant en local sur le Mac, avec les vrais luminaires** :

```sh
cd ha-integration
uv venv --python 3.14 .venv-ha
uv pip install -p .venv-ha "homeassistant==2026.11.*"
mkdir -p ~/.hass_dev/custom_components
ln -s "$PWD/custom_components/phs16lc" ~/.hass_dev/custom_components/phs16lc   # code live
.venv-ha/bin/hass -c ~/.hass_dev     # 1er lancement long (deps) → http://localhost:8123
```

- L'intégration se configure dans l'UI avec le port `/dev/cu.usbserial-XXXX`.
- Le symlink rend le code du dépôt **live** : après chaque modification,
  redémarrer `hass` (Ctrl-C puis relancer) pour recharger.
- **Pourquoi pas de conteneur sur le Mac** : le passthrough USB des ports série
  vers un conteneur (Docker Desktop, ou `container` d'Apple sur macOS 26) reste
  fragile ; le venv accède directement à `/dev/cu.usbserial-XXXX`. Sur le Mac,
  Docker ne sert que pour des tests sans matériel (pty).

## 4. Modèle d'entités (figé)

Un *device* HA par carte SPOT (« SPOT 1 », « SPOT 2 »…), relié (`via_device`)
au device hub « Adaptateur PHS16-LC » (identifié par le port série / USB).

| Entité | Type | Rôle |
| --- | --- | --- |
| `light.phs16lc_spot_<n>` | `light` | On/off + luminosité (mA, voir D10). `turn_on(brightness)` = tous les canaux au même courant (équiv. `phs16ctl on <n> <mA>`) |
| `select.phs16lc_spot_<n>_recette` | `select` | Options = recettes du dossier configuré. Sélection = `apply_recipe` complet |
| `select.phs16lc_spot_<n>_groupe` | `select` | Options = groupes de la recette courante + « (tous) ». Sélection = application partielle (`--group`) |
| `button.phs16lc_spot_<n>_save_nvm` | `button` | `@WP` : rend les courants permanents en NVM |
| `button.phs16lc_scene_<nom>` | `button` | Applique un fichier de scène (`scenes/*.json`) via `apply_scene` |
| `button.phs16lc_scan` | `button` | Rescan de la ligne (découverte des adresses) |
| `sensor.phs16lc_spot_<n>_temperature_cpu` / `_led1` / `_led2` | `sensor` | `device_class: temperature`, `state_class: measurement`, unité °C (`@GT`) |
| `sensor.phs16lc_spot_<n>_courants` | `sensor` | Résumé texte des courants (`format_currents`) + attribut détaillé `channels: [mA…]` |
| `binary_sensor.phs16lc_spot_<n>_en_ligne` | `binary_sensor` | Présence de la carte (répond au `@GI` pendant le scan/polling) |

## 5. Services exposés (figés)

| Service | Champs | Action |
| --- | --- | --- |
| `phs16lc.scan` | — | Rescan complet, rapport dans le log + notification d'événement |
| `phs16lc.apply_recipe` | `address` (int ou `all`), `recipe` (fichier), `group?` | `apply_recipe` (+ événement `phs16lc_recipe_applied`) |
| `phs16lc.apply_scene` | `file`, `save?` | `apply_scene` (+ événement `phs16lc_scene_applied`) |
| `phs16lc.save` | `address` | `@WP` (+ événement `phs16lc_saved`) |
| `phs16lc.set_channels` | `address`, `currents` (liste mA, 16 valeurs) | `set_channels` (réglage canal par canal avancé) |
| `phs16lc.set_channel` | `address`, `channel` (1–16), `ma` | Un seul canal |

## 6. Phases de développement

### Phase 0 — Cadrage et squelette — FAITE (2026-11-11)
- [x] Décisions figées (D1–D18) et plan rédigé.
- [x] Arborescence `ha-integration/` + `manifest.json` + `hacs.json` + `brand/` (icon.png 512×512, logo.png 1024×256 générés par `tools/make_brand.py`).
- [x] `manifest.json` conforme hassfest 2026.11 : clés requises présentes, **pas** de clé `homeassistant` (dans `hacs.json`), `requirements: ["pyserial==3.5"]` (pin identique `package_constraints.txt` HA 2026.11), `categories: ["lighting.lighting_systems"]`, `usb` VID `0403`/PID `6001`, `integration_type: "hub"`, `iot_class: "local_polling"`.
- [x] `tools/sync_phs16ctl.py` + première copie vendored de `phs16ctl` (5 modules, `cli.py` exclu) dans `custom_components/phs16lc/phs16ctl/`.
- [x] `config_flow.py` : port série (détection `list_ports` en executor + saisie manuelle), `expected_spots`, `poll_interval` (5–60 s), `recipes_dir` ; unique_id = port.
- [x] `services.yaml` (6 services) + `strings.json` + `translations/en.json` + `fr.json` + `README.md` + `pyproject.toml` (dev: `homeassistant==2026.11.*`, `pytest-homeassistant==2026.11.*`).
- [x] Tests phase 0 (10 tests, sans runtime HA) : manifest/hacs/brand/translations/services + synchro vendored — **10 passed** (`uv run --no-project --with pytest --with pyyaml --python 3.14 pytest tests/`).

### Phase 1 — Hub + coordinator — FAITE (2026-11-11)
- [x] `__init__.py` : ouverture `PhsLink` en executor (`ConfigEntryNotReady` si port indisponible → retry auto), coordinator + `async_config_entry_first_refresh`, unload ferme le port.
- [x] `coordinator.py` : scan initial (`scan_line` + `expected_spots`), polling `@GI`/`@GP`/`@GT` toutes les `poll_interval` s, `async_rescan()`, `async_io()` (lock asyncio + executor : un seul thread sur le port, D7/D8).
- [x] Registre de devices (`entity.py`) : hub « PHS16-LC <port> » + device « SPOT n » en `via_device`.
- [x] `binary_sensor` de présence par SPOT, ajout dynamique à chaque rescan.
- [x] Tests (FakePhsLink, fixtures `pytest-homeassistant`) : flow, setup+scan, doublon de port, carte muette au polling, rescan avec nouvelle carte, unload ferme le port, port indisponible → SETUP_RETRY. **17 tests passed**.
- [x] Note : contrat `DataUpdateCoordinator._async_setup` changé en HA 2026.11 (retourne `None`, renseigne `self.data`) — corrigé et couvert par les tests.

### Phase 2 — Entité `light` — FAITE (2026-11-11)
- [x] `light.py` : `SpotLight` (entité principale du device « SPOT n », `name=None`), `ColorMode.BRIGHTNESS` ; état on = au moins un canal ≥ 74 mA, brightness = courant max (D10) ; `turn_on(brightness)` = tous canaux à `brightness_to_ma(b)` ; `turn_on()` sans luminosité = dernière recette (`SpotState.last_recipe`) sinon 500 mA (D11) ; `turn_off()` = zéros ; carte muette → `HomeAssistantError`.
- [x] `coordinator.py` : commandes `async_set_channels` / `async_apply_recipe` / `async_save` (I/O via `async_io`), `SpotState.last_recipe` ; **refresh direct** (`async_refresh`, pas le debouncer) après chaque commande pour un état immédiat.
- [x] `const.py` : `ma_to_brightness` renvoie au moins 1 si allumé (≥ 74 mA).
- [x] Tests : mapping mA↔brightness (aller-retour), état reflété par le polling, recette non uniforme (brightness = max), turn_on avec/sans brightness, réapplication recette (D11), turn_off, carte muette → erreur. **25 tests passed**.

### Phase 3 — `select` recette + groupe
- [ ] Scan du dossier recettes (recipes_dir) → options des selects.
- [ ] Application complète / partielle via executor + événement `phs16lc_recipe_applied`.
- [ ] Tests : recette inconnue, groupe inconnu, validation bornes (héritée de `Recipe.validate`).

### Phase 4 — `button`s
- [ ] `save_nvm` par carte, `scene_<nom>` par fichier de scène, `scan`.
- [ ] Tests : `@WP`, scène multi-cartes avec une carte en erreur.

### Phase 5 — `sensor`s
- [ ] Températures CPU/LED1/LED2 (device_class temperature), courants (résumé + attribut), état de la ligne.
- [ ] Tests : décodage `@GT`, carte muette → `unavailable`.

### Phase 6 — Services + traductions
- [ ] `services.yaml` + handlers (section 5), `translations/fr.json` + `en.json`.
- [ ] Tests : chaque service avec FakeLink.

### Phase 7 — Polissage
- [ ] Options flow (poll_interval, expected_spots, recipes_dir) + reconfigure.
- [ ] `diagnostics.py` (infos carte `@GL`, ports détectés, version intégration).
- [ ] Événements logbook complets, README de l'intégration.
- [ ] Validation hassfest du manifest (`homeassistant` absent du manifest, `categories` présent, requirements compatibles core).

### Phase 8 — Validation sur MacBook Pro (sans puis avec matériel)
- [ ] E2E sans matériel : `fake_spot.py --boards 3` sur pty → instance HA locale du Mac (`hass -c ~/.hass_dev`, port = le pty) → scénario : scan, on/off, recette, groupe, scène, save, températures.
- [ ] Validation avec vrais luminaires branchés sur le Mac : checklist du GUIDE §3.5.

### Phase 9 — Déploiement sur le PC Linux dédié
- [ ] Installer HA (OS ou Container) sur le mini-PC — GUIDE §4.
- [ ] Copier `custom_components/phs16lc/` dans `/config/custom_components/` (ou dépôt privé + Marketplace) — **aucun changement de code** (D18).
- [ ] Reconfigurer l'intégration avec `/dev/ttyUSB0` (règle udev `/dev/phs16bus` recommandée, GUIDE §6).
- [ ] Rejouer la checklist de validation (GUIDE §4.5) sur le vrai bus en production.
- [ ] Mise à jour du GUIDE avec captures/retours d'expérience.

## 7. Stratégie de test

Tout se déroule sur le MacBook Pro (boucle de développement §3.1).

- **Unitaire** : `pytest-homeassistant` (épinglé HA 2026.11.x) + `FakeLink` (même technique que `phs16ctl/tests/`) → aucune I/O réelle.
- **End-to-end sans matériel** : `../light-monitor/tools/fake_spot.py --boards N` crée un port pty qui simule les SPOT ; l'instance HA locale du Mac (`hass -c ~/.hass_dev`) y accède directement en configurant le pty comme port série.
- **End-to-end avec vrais luminaires sur le Mac** : checklist du GUIDE §3.5 (scan, on/off, recette, scène, @WP + persistance après coupure, alerte température, carte muette au milieu du bus).

## 8. Risques et contraintes

| Risque | Mitigation |
| --- | --- |
| Port série ouvert deux fois (CLI + HA) | Règle documentée (D7) ; l'intégration logue une erreur claire si le port est indisponible |
| I/O bloquant qui fige HA | Tout `PhsLink.send` en executor (D8) |
| Le scan s'arrête au premier silence (trou dans la ligne) | `expected_spots` (config flow) pour poursuivre et signaler les muettes — même option que `--expected` de la CLI |
| `@SP` volatile | Bouton « save NVM » + option `save` des services ; rappel dans le GUIDE |
| hassfest renforcé (2026.11) | Pas de clé `homeassistant` dans `manifest.json` (dans `hacs.json`), `categories` renseigné, `requirements` = pin core pour pyserial |
| Marketplace = code communautaire non audité | Distribution privée uniquement (D4) |
| HA 2026.11 valide l'environnement Python au boot | venv de dev en Python 3.14, cohérent avec HA 2026.11 |
| Nommage des entités modifié en 2026.11 | Installation neuve : aucun impact ; à noter si migration d'une instance existante |

## 9. Journal des décisions (modifications ultérieures)

| Date | Décision | Modification | Motif |
| --- | --- | --- | --- |
| 2026-11-11 | D1–D16 | Cadrage initial | Lancement du développement |
| 2026-11-11 | D16–D18 | Ajout dev local MacBook Pro + déploiement Linux sans changement de code ; harnais de test = `pytest-homeassistant` (package central 2026.11) | Développement/test sur ce Mac (macOS 26.6, FTDI VCP à valider, port `/dev/cu.usbserial-XXXX`), puis déploiement sur PC Linux (`/dev/ttyUSB0`) avec le même code |
| 2026-11-11 | Phase 0 | Squelette créé : manifest/hacs.json/brand/config_flow/services/strings+translations, `sync_phs16ctl.py` + copie vendored (5 modules), pyproject, 10 tests OK | Démarrage de l'implémentation ; pin pyserial==3.5 = pin HA core 2026.11 (vérifié dans `package_constraints.txt`) ; catégorie `lighting.lighting_systems` (catégories 2026.11 hiérarchiques) |
| 2026-11-11 | Phase 1 | `coordinator.py` + `entity.py` + `binary_sensor.py` + setup/unload dans `__init__.py` ; 17 tests passed (FakePhsLink + pytest-homeassistant) | Contrat `_async_setup` 2026.11 (set `self.data`, retourne None) découvert via les tests et corrigé ; `async_io()` sérialise l'accès au port série |
| 2026-11-11 | Phase 2 | `light.py` (ColorMode.BRIGHTNESS, mapping D10, D11) + commandes du coordinator ; 25 tests passed | Après une commande, refresh direct (`async_refresh`) au lieu du debouncer — sinon l'état restait à la valeur précédente dans les 10 s de cooldown |
