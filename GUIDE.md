# GUIDE — Intégration Home Assistant `phs16lc`

Choix du matériel, installation (hardware + software) et utilisation de
l'intégration Home Assistant qui pilote les luminaires **PHS16-LC** à distance.

> **Document vivant** — mis à jour au fur et à mesure du développement.
> Version : 0.4 — 2026-11-11 — benchmark mini-PC N100 et shortlist documentés (§2.1).
> Version : 0.3 — 2026-11-11 — question « Mac mini refurbished ? » tranchée et
> documentée (§2.1.1) : machine dédiée = PC Linux, Mac réservé au développement.
> Version : 0.2 — 2026-11-11 — ajout du développement/test local sur MacBook Pro (§3)
> et de la procédure de déploiement sur le PC Linux dédié (§4).
> Version : 0.1 — 2026-11-11 — état : installation/usage prévus, intégration en
> cours de développement (voir [`PLAN.md`](PLAN.md)).
> Le protocole et le câblage du bus sont détaillés dans [`../GUIDE.md`](../GUIDE.md)
> (adaptateur USB-RS422, pinout RJ45, sertissage) et [`../README.md`](../README.md).

---

## 1. Vue d'ensemble

L'intégration `phs16lc` fait le lien entre Home Assistant et le bus RS-485
des luminaires PHS16-LC :

```
Appli mobile / navigateur ──► Home Assistant ──► intégration phs16lc ──► /dev/ttyUSB0
                                                                    │  (pyserial, cœur = phs16ctl)
                                                                    ▼
                                              FTDI USB-RS422-WE ──► bus RS-485 ──► SPOT 1..N
        ▲
        └── accès à distance via le VPN de l'entreprise (aucun port ouvert, pas de cloud)
```

Ce que cela apporte :

- **Interface prête à l'emploi** : tableau de bord web + appli mobile officielle,
  sans rien développer côté UI.
- **Pilotage par luminaire** : on/off, intensité (mA), recettes lumineuses,
  scènes multi-cartes, sauvegarde en mémoire permanente (NVM).
- **Supervision** : températures de chaque carte, présence, courants appliqués.
- **Historique** : états et températures enregistrés par HA (History / Statistics),
  actions journalisées dans le *logbook*.
- **Automations** : photopériode, alertes de température, recettes au boot…
  pouvant aussi réagir à d'autres capteurs (température extérieure, etc.).
- **Local-first** : tout fonctionne sans Internet ; le VPN ne sert que d'accès distant.

Le **développement et les tests** se font sur un MacBook Pro avec les luminaires
branchés en USB (§3) ; le **déploiement** sur la machine dédiée (mini-PC/Pi) est
au §4 — aucun changement de code entre les deux (voir PLAN D18).

---

## 2. Choix du matériel

### 2.1 Le mini-PC dédié

La machine reste allumée en permanence et Home Assistant écrit beaucoup
(l'historique des capteurs) : **le stockage sur SSD est obligatoire**
(une carte SD s'userait en quelques mois).

| Option | Matériel indicatif | RAM / stockage | Avantage | Inconvénient |
| --- | --- | --- | --- | --- |
| **Raspberry Pi 5** (recommandé si préférence Pi) | Pi 5 8 Go + SSD USB3 ou HAT NVMe | 8 Go / SSD 256 Go+ | Compact, sobre, bien supporté par HA OS | Un peu juste en 24/7 avec beaucoup d'historique |
| **Mini-PC x86 (recommandé)** | Intel N100 (ex: Lenovo ThinkCentre Tiny, Dell Wyse, Beelink EQ12), neuf ou reconditionné | 16 Go / SSD 256 Go+ | Plus robuste et durable en continu, souvent moins cher qu'un Pi 5 bien équipé, plus de ports USB | Encombrement un peu supérieur |

**Recommandation** : un **mini-PC N100 avec 16 Go de RAM et un SSD de 256 Go minimum**,
installé près du tableau/luminaires, branché en Ethernet sur le réseau de
l'entreprise. Un Pi 5 + SSD fait aussi très bien l'affaire.

#### Un Mac mini reconditionné ? (question écartée le 2026-11-11)

Non pour la machine dédiée. Le matériel est excellent (silencieux, ~4–6 W au
repos), mais :

- **HA n'a pas d'installation production supportée sur macOS** : depuis la
  dépréciation de mai 2025, seules HA OS et Container sont officielles, le venv
  macOS ne sert qu'au développement — et HA 2026.11 refuse de démarrer hors
  venv/conteneur. HA OS ne tourne pas nativement sur macOS.
- Sur Mac, il faudrait HA en conteneur (Docker Desktop = VM Linux cachée :
  *host networking* cassé, **passthrough USB série peu fiable** — or le bus
  USB-RS422 est le cœur du projet) ou en venv (non supporté en production, pas
  de Supervisor, pas d'add-ons, pas de sauvegardes intégrées).
- Il coûte **2 à 3× plus cher** (M1 refurb ~450–490 €, M2 ~560 € en 2026) qu'un
  mini-PC N100 (~150–250 € neuf, ~80–150 € refurb) ou un Pi 5 + SSD (~150–200 €).

Le Mac mini n'a d'intérêt ici que comme machine de **développement** — rôle déjà
rempli par le MacBook Pro (§3). Le déploiement cible reste un PC Linux (§4).

#### Benchmark mini-PC — shortlist (2026-11-11)

**Filtre de compatibilité obligatoire** : HA OS 2026.11 exige x86-64-v3
(AVX2/FMA). Les **N100/N97/N150/N200 sont compatibles** (Gracemont = v3) ;
les **N5105/J4125/J6412 sont v2 uniquement → exclus** (ex: MeLE Quieter3C
en N5100 est exclu, le Quieter4C en N100 est OK).

**Config minimale pour cette application** : 16 Go RAM, SSD NVMe 256–512 Go
(jamais eMMC seul — le recorder HA écrit beaucoup), 1 GbE, 1 USB 3.0 pour
l'adaptateur FTDI, châssis métal fanless de préférence, UEFI + Secure Boot
désactivable (image HAOS generic x86-64 écrite directement sur le SSD interne).

| Option | Modèle | Prix indicatif (nov. 2026) | Pourquoi |
| --- | --- | --- | --- |
| Meilleur rapport qualité/prix neuf | Beelink EQ12 ou Mini S12 Pro, NiPoGi AK1PLUS (variante **N100/N97**, 16 Go/512 Go) | ~140–230 € | Éprouvés pour HA ; prendre impérativement la config 16 Go + NVMe |
| Meilleure robustesse 24/7 | **ThinkCentre M90q/M720q Tiny** ou **HP EliteDesk 800 G5 Mini**, **Dell OptiPlex Micro** reconditionnés (i3/i5 9e–10e gen) | ~110–200 € (Back Market, Recommerce, Amazon Renewed) | Châssis pro, RAM/SSD remplaçables, silencieux, v3 OK |
| Meilleure intégration PHS16 | **Qotom Q10900X-S04** (N100/N305, COM RS-485 natif, fanless) | ~250–350 € (qotom.com, AliExpress) | Bus RS-485 en direct, sans adaptateur USB ; **vérifier que le COM est RS-485 full-duplex 4 fils** (TX±/RX±), comme l'exige le bus PHS16 |
| Fanless grand public | Beelink EQ14 (N150, 2×2.5GbE, alim interne), MeLE Quieter4C/DL | ~160–280 € | Silence 0 dB, prévu 24/7 |

Liens : [idealo.fr mini PC N100](https://www.idealo.fr/liste/122870085/mini-pc-n100.html) ·
[Amazon.fr mini PC N100 16 Go](https://www.amazon.fr/s?k=mini+pc+N100+16+Go+512+Go) ·
[Clubic Beelink EQ12](https://www.clubic.com/516355-beelink-eq12-n100.html) ·
[raspberry.tips HA 2026 Pi5 vs N100](https://raspberry.tips/en/smart-home/home-assistant-hardware-2026-raspberry-pi-5-or-n100-mini-pc) ·
[techfuelhq best mini PC HA 2026](https://techfuelhq.com/homelab/best-mini-pc-home-assistant-2026/) ·
[Back Market ThinkCentre Tiny](https://www.backmarket.com/fr-fr/search?q=thinkcentre+tiny) ·
[Qotom Q10900X-S04](https://www.qotom.com/products/show/MinI-PC-Q10900X-S04-Series).
Prix à revérifier au moment de l'achat (Black Friday : 27/11/2026). **Pièges** :
CPU v2 (N5105/J4125/J6412), eMMC seul, RAM soudée seule, configs 8 Go/256 Go.

Points communs : alimentation stable (mini UPS/ondulineur advised si coupures
fréquentes — les `@SP` sont volatils, seule la NVM (`@WP`) survit à une coupure),
câble Ethernet, accès au réseau de l'entreprise (IP fixe ou DHCP réservé conseillé).

### 2.2 Adaptateur USB → RS-422 (full duplex, obligatoire)

| Élément | Détail |
| --- | --- |
| Modèle retenu | **FTDI USB-RS422-WE-1800-BT** (datasheet `../0900766b80da71a2.pdf`) |
| Pourquoi | Le bus PHS16-LC est en **RS-485 full duplex 4 fils** (TX+, TX−, RX+, RX−). Ne **pas** utiliser le câble USB-RS485-WE (half-duplex 2 fils). |
| Côté bus | 5 fils nus : TX+ (Y), TX− (Z), RX+ (A), RX− (B), GND |
| Côté PC | `/dev/ttyUSB0` sous Linux, pilote noyau `ftdi_sio` inclus, rien à installer |
| Détection | `ls /dev/ttyUSB*` ou, une fois l'intégration installée, la liste proposée dans le formulaire de configuration |

Câblage du bus (pinout RJ45 T568B, sertissage, terminaison 100 Ω, topologie
linéaire) : voir [`../GUIDE.md`](../GUIDE.md) §1.2 — ne pas réinventer ici.

### 2.3 Récapitulatif du matériel à acheter

- [ ] Mini-PC N100 16 Go + SSD 256 Go (ou Raspberry Pi 5 8 Go + SSD USB/NVMe)
- [ ] Câble Ethernet (branchement au réseau entreprise)
- [ ] Adaptateur **FTDI USB-RS422-WE-1800-BT** (full duplex 4 fils)
- [ ] Câble bus Cat5e/Cat6a/Cat7 + connecteurs RJ45 blindés (voir GUIDE racine §1.2)
- [ ] (Optionnel) petit onduleur (UPS) pour éviter les coupures de courant

---

## 3. Développement et tests locaux sur MacBook Pro (cette machine)

Tout le développement se fait sur ce MacBook Pro (macOS 26.6.2, Apple Silicon),
y compris avec les **vrais luminaires branchés en USB**. Le déploiement final sur
le PC Linux est décrit au §4 : **aucun changement de code** n'est nécessaire
(l'intégration est en pur Python + pyserial ; seul le nom du port série diffère).

### 3.1 Prérequis macOS

- **Python 3.14 via `uv`** (déjà installé sur cette machine) : Home Assistant
  2026.11 exige Python ≥ 3.14.2 **et** un venv (contrôle au boot) — le `python3`
  système (3.9) est trop vieux, toujours passer par `uv`.
- **Pilote FTDI VCP** (macOS ≥ 26.6 ne l'inclut plus) : installer depuis
  <https://ftdichip.com/drivers/vcp-drivers/>, puis valider l'extension dans
  *Réglages Système → Confidentialité et sécurité*, redémarrer. Le câble
  USB-RS422-WE apparaît alors en `/dev/cu.usbserial-XXXX` (préfixe `cu.`, pas
  `tty.` ; vérifier avec `ls /dev/cu.usbserial*`). Voir `../README.md` §7.2.
- Brancher l'adaptateur USB-RS422-WE et le bus des luminaires (câblage : §2.2
  et `../GUIDE.md` §1.2).

### 3.2 Tester le backend `phs16ctl` seul (sans Home Assistant)

```sh
cd phs16ctl
uv sync
uv run pytest                                        # tests unitaires (FakeLink, sans matériel)
uv run phs16ctl --list-ports                         # doit lister /dev/cu.usbserial-XXXX
uv run phs16ctl --port /dev/cu.usbserial-XXXX scan   # vrais luminaires
uv run phs16ctl --port /dev/cu.usbserial-XXXX on 1 800
uv run phs16ctl --port /dev/cu.usbserial-XXXX status 1
```

Sans luminaire (simulateur sur port pty) :

```sh
python3 ../light-monitor/tools/fake_spot.py --boards 3 > /tmp/port.txt 2>/tmp/trames.log &
sleep 1
cd phs16ctl && uv run phs16ctl --port "$(cat /tmp/port.txt)" scan
```

### 3.3 Tests unitaires de l'intégration HA

```sh
cd ha-integration
uv venv --python 3.14 .venv
uv pip install -p .venv "homeassistant==2026.11.*" "pytest-homeassistant==2026.11.*" pytest pyserial
uv run --python .venv/bin/python pytest tests/ -v     # fixtures HA + FakeLink, aucune I/O réelle
```

> Harnais de test : `pytest-homeassistant` (package central officiel, version
> 2026.11.x) — l'ancien `pytest-homeassistant-custom-component` est abandonné.

### 3.4 Faire tourner Home Assistant en local sur le Mac (vrais luminaires)

Option recommandée : **Home Assistant Core en venv directement sur macOS**
(installation « manuelle » officielle, supportée pour le développement ; macOS
n'est pas une plateforme de production) :

```sh
cd ha-integration
uv venv --python 3.14 .venv-ha
uv pip install -p .venv-ha "homeassistant==2026.11.*"
mkdir -p ~/.hass_dev/custom_components
ln -s "$PWD/custom_components/phs16lc" ~/.hass_dev/custom_components/phs16lc   # code live
.venv-ha/bin/hass -c ~/.hass_dev     # 1er lancement long (deps) → http://localhost:8123
```

- Ajouter l'intégration **PHS16-LC** dans l'UI (Réglages → Appareils et services)
  avec le port `/dev/cu.usbserial-XXXX`.
- Le symlink rend le code du dépôt **live** : après chaque modification,
  redémarrer `hass` (Ctrl-C puis relancer) pour recharger l'intégration.
- **Pourquoi pas de conteneur sur le Mac** : le passthrough USB des ports série
  vers un conteneur (Docker Desktop, ou `container` d'Apple sur macOS 26) reste
  fragile ; le venv accède directement à `/dev/cu.usbserial-XXXX`. Sur le Mac,
  Docker ne sert que pour des tests sans matériel (port pty).

### 3.5 Checklist de validation avec les vrais luminaires (sur le Mac)

- [ ] Scan : toutes les cartes apparaissent (« SPOT 1 », « SPOT 2 »…) avec le capteur « en ligne ».
- [ ] On/off + luminosité depuis le tableau de bord → les vraies LED réagissent ; le mA lu correspond au curseur.
- [ ] Recette complète, puis groupe partiel (listes déroulantes « Recette » / « Groupe »).
- [ ] Scène multi-cartes (bouton « Scène … »).
- [ ] « Sauvegarder NVM » puis coupure de l'alimentation d'un luminaire → les courants sont conservés au redémarrage.
- [ ] Températures remontées et historisées (barre latérale « Historique ») ; alerte > 70 °C testée.
- [ ] Carte éteinte au milieu du bus → signalée « hors ligne » grâce au réglage « nombre de SPOT attendus ».

---

## 4. Installation sur le PC Linux dédié (déploiement)

Cette section décrit l'installation sur la **machine cible dédiée** (mini-PC ou
Pi du §2.1), celle qui restera allumée près des luminaires. Deux voies selon le
matériel choisi. **Home Assistant OS** est recommandé : c'est l'installation la
plus plug-and-play (mises à jour, add-ons, sauvegardes intégrées, supervisor).

### 4.1 Option A — Home Assistant OS (recommandé)

1. Télécharger l'image « Raspberry Pi 5 » ou « Generic x86-64 » sur
   <https://www.home-assistant.io/installation/> (version **2026.11.x** ou plus récente).
2. Flasher l'image sur le SSD (avec Raspberry Pi Imager, Balena Etcher, ou `dd`).
3. Démarrer la machine (SSD + Ethernet branchés, adaptateur USB-RS422 branché).
4. Au premier boot, attendre ~20 min, puis ouvrir `http://homeassistant.local:8123`
   (ou l'IP affichée) et créer le compte administrateur (onboarding).
5. (Optionnel) Installer l'add-on **Terminal & SSH** (Réglages → Add-ons → Boutique)
   pour le dépannage en ligne de commande.

> Depuis la **2026.11**, le **Marketplace** (Réglages → Marketplace) est intégré
> nativement : plus besoin d'installer HACS séparément (l'ancien HACS est même
> bloqué sur ≥ 2026.11).

### 4.2 Option B — Debian générique + Home Assistant en conteneur

Pour un mini-PC sur lequel on veut garder la main sur le système :

```sh
# Debian 12/13 à jour, Docker installé
sudo docker run -d \
  --name homeassistant \
  --privileged \
  --restart=unless-stopped \
  -e TZ=Europe/Paris \
  -v /path/to/config-ha:/config \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
```

- `--device /dev/ttyUSB0` : passe l'adaptateur USB-RS422 au conteneur
  (vérifier le port avec `ls /dev/ttyUSB*` ; le rendre stable via une règle udev
  sur le numéro de série FTDI, voir §6).
- Premier accès : `http://<ip-du-mini-pc>:8123`, onboarding idem.

### 4.3 Installer l'intégration `phs16lc`

L'intégration vit dans ce dépôt : [`custom_components/phs16lc/`](custom_components/phs16lc/).

**Méthode 1 — copie manuelle (recommandée pour un usage privé)** :

```sh
# Sur la machine HA (via l'add-on Terminal & SSH, ou en copiant le dossier à la main)
mkdir -p /config/custom_components
# copier le dossier custom_components/phs16lc/ du dépôt vers /config/custom_components/phs16lc/
# puis redémarrer Home Assistant (Réglages → Système → Redémarrer)
```

**Méthode 2 — dépôt git privé + Marketplace** (mises à jour en un clic, avec
entité « update ») : pousser ce dossier `ha-integration/` sur un dépôt git privé,
puis dans HA : Réglages → Marketplace → ⋮ → **Dépôts personnalisés** → ajouter
l'URL du dépôt, catégorie « Intégrations », puis installer `phs16lc`.
Le dépôt doit contenir `hacs.json` (présent) et les fichiers sous
`custom_components/phs16lc/`.

> Le Marketplace affiche un avertissement : le contenu communautaire n'est ni
> testé ni supporté par le projet Home Assistant. C'est attendu pour une
> intégration privée.

### 4.4 Premier paramétrage de l'intégration

Réglages → Appareils et services → **Ajouter une intégration** → chercher
**« PHS16-LC »** → formulaire :

| Champ | Valeur | Détail |
| --- | --- | --- |
| Port série | `/dev/ttyUSB0` sur le PC Linux (liste déroulante des ports détectés, ou saisie manuelle) ; `/dev/cu.usbserial-XXXX` sur le Mac de développement (§3) | L'adaptateur FTDI doit être branché |
| Nombre de SPOT attendus | ex: `4` | Le scan s'arrête au premier silence ; ce réglage permet de détecter une carte HS au milieu de la ligne (équivalent `--expected` de la CLI) |
| Intervalle de rafraîchissement | `10` s (5–60) | Le protocole ne pousse pas d'état : HA interroge les cartes (`@GP`, `@GT`) à cet intervalle |
| Dossier des recettes | `/config/phs16lc/recipes` | Copier `../phs16ctl/recipes/*.json` et `../phs16ctl/scenes/*.json` à cet endroit |

```sh
# Copier recettes et scènes dans la config HA (exemple, via Terminal & SSH)
mkdir -p /config/phs16lc/recipes /config/phs16lc/scenes
cp /chemin/du/depot/phs16ctl/recipes/*.json /config/phs16lc/recipes/
cp /chemin/du/depot/phs16ctl/scenes/*.json  /config/phs16lc/scenes/
```

### 4.5 Vérification de l'installation

1. **Scan** : appuyer sur le bouton « Scanner la ligne » (ou service
   `phs16lc.scan`) → les cartes détectées apparaissent comme *devices*
   (« SPOT 1 », « SPOT 2 »…) reliés au hub « Adaptateur PHS16-LC ».
2. **Entités** : chaque SPOT a une lampe (`light`), deux listes déroulantes
   (recette / groupe), un bouton « Sauvegarder NVM », 3 capteurs de température,
   un résumé des courants et un capteur de présence.
3. **Test rapide** : allumer/éteindre la lampe « SPOT 1 » depuis le tableau de
   bord, vérifier que les vraies LED réagissent.
4. Sans matériel, on peut valider tout le flux avec le simulateur :
   `../light-monitor/tools/fake_spot.py --boards 3` (voir PLAN §3.1).

### 4.6 Accès à distance

La machine est sur le réseau de l'entreprise, joignable depuis l'extérieur via
le **VPN existant** : aucun port à ouvrir, aucun service cloud requis.

- **Navigateur** : `http://<ip-de-la-machine>:8123` une fois le VPN connecté.
- **Appli mobile** (iOS/Android, gratuite) : ajouter l'instance avec l'IP interne
  (Réglages de l'appli → serveur interne) ; en déplacement, via le VPN.
- **Sécurité** : ne jamais exposer le 8123 sur Internet directement ; garder
  l'authentification HA (mot de passe + 2FA recommandé) ; mises à jour HA
  régulières (Réglages → Mises à jour, le Marketplace fournit aussi une entité
  « update » pour l'intégration `phs16lc` si installée via dépôt privé).

---

## 5. Utilisation

### 5.1 Les entités par luminaire

| Entité | Utilisation |
| --- | --- |
| Lampe « SPOT n » | On/off + curseur de luminosité. Le curseur 1–100 % est converti en **mA réels** (74–2150 mA, linéaire). « On » sans curseur = réapplique la dernière recette, ou 500 mA si aucune. |
| Liste « Recette » | Choisir une recette du dossier configuré → appliquée en entier à la carte. |
| Liste « Groupe » | Choisir un groupe de la recette (ex: « rouge ») → application partielle (les autres canaux restent tels quels). |
| Bouton « Sauvegarder NVM » | Rend les courants actuels **permanents** dans la carte (`@WP`). Sans ça, ils sont perdus à la mise hors tension. |
| Boutons « Scène … » | Appliquent un fichier de scène à plusieurs cartes d'un coup. |
| Bouton « Scanner la ligne » | Redécouvre les cartes présentes. |
| Capteurs « Température CPU / LED 1 / LED 2 » | °C, enregistrés dans l'historique. |
| Capteur « Courants » | Résumé (ex: « 800 mA × 8 + 0 × 8 ») + détail canal par canal en attributs. |
| Capteur « En ligne » | Présence de la carte sur le bus. |

### 5.2 Allumer / éteindre / régler l'intensité

- Carte par carte via la lampe, ou **toutes les cartes** via une automation
  ciblant `light.phs16lc_spot_*` (ou le service `phs16lc.apply_recipe` avec
  `address: all`).
- Correspondance curseur → courant : `mA = 74 + (2150 − 74) × % / 100`
  (ex: 50 % ≈ 1112 mA). En dessous de 74 mA, le canal est éteint.

### 5.3 Recettes lumineuses et scènes

Les recettes sont les fichiers JSON copiés dans `/config/phs16lc/recipes/`
(format documenté dans [`../GUIDE.md`](../GUIDE.md) §5 : vecteur `channels`
ou `groups`). Pour en ajouter : copier le fichier dans ce dossier, puis
« Scanner » ou redémarrer l'intégration pour rafraîchir les listes.

Les scènes (`/config/phs16lc/scenes/*.json`) apparaissent comme des boutons
« Scène <nom> ».

### 5.4 Supervision et historique

- **Historique** (barre latérale « Historique ») : courbes de température et
  états des lampes, sur la durée de rétention configurée
  (Réglages → Système → Statistiques → ou `recorder:` dans `configuration.yaml`).
- **Logbook** : chaque recette/scène/sauvegarde apparaît comme événement
  (`phs16lc_recipe_applied`, `phs16lc_scene_applied`, `phs16lc_saved`).
- **Statistiques** : pour grapher les températures sur le long terme.

### 5.5 Exemples d'automations (YAML)

Automatisation visuelle ou YAML (Réglages → Automatisations) :

```yaml
# Photopériode : recette « croissance » à 6h, extinction à 22h
alias: Photopériode serre
trigger:
  - platform: time
    at: "06:00:00"
  - platform: time
    at: "22:00:00"
action:
  - choose:
      - conditions: "{{ trigger.now.hour == 6 }}"
        sequence:
          - service: phs16lc.apply_recipe
            data:
              address: all
              recipe: croissance.json
      - conditions: "{{ trigger.now.hour == 22 }}"
        sequence:
          - service: light.turn_off
            target:
              entity_id: light.phs16lc_spot_1
```

```yaml
# Alerte si une carte dépasse 70 °C
alias: Alerte température PHS16
trigger:
  - platform: numeric_state
    entity_id:
      - sensor.phs16lc_spot_1_temperature_cpu
      - sensor.phs16lc_spot_2_temperature_cpu
    above: 70
action:
  - service: notify.mobile_app_<ton_telephone>
    data:
      title: PHS16-LC
      message: "{{ trigger.entity_id }} dépasse 70 °C"
```

```yaml
# Au démarrage de HA : réappliquer le profil « default » (recette du boot)
alias: Boot PHS16
trigger:
  - platform: homeassistant
    event: start
action:
  - service: phs16lc.apply_recipe
    data:
      address: all
      recipe: croissance.json
```

### 5.6 Services avancés

Disponibles dans Outils de développement → Services :
`phs16lc.scan`, `phs16lc.apply_recipe`, `phs16lc.apply_scene`, `phs16lc.save`,
`phs16lc.set_channels` (16 valeurs mA), `phs16lc.set_channel` (un canal).

### 5.7 Coexistence avec la CLI `phs16ctl`

La CLI (`../phs16ctl/`) et l'intégration HA **ne doivent pas tourner en même
temps sur le même port série** (`/dev/ttyUSB0` ne s'ouvre qu'une fois).
Pour intervenir en CLI : retirer temporairement l'intégration
(Réglages → Appareils et services → PHS16-LC → Supprimer), ou utiliser un
autre port/adaptateur.

---

## 6. Dépannage

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| Aucune entité après l'ajout de l'intégration | Dossier mal copié / pas de redémarrage | Vérifier `/config/custom_components/phs16lc/manifest.json`, redémarrer HA, voir les logs (Réglages → Système → Journaux) |
| « Impossible d'ouvrir le port » | Mauvais port, ou port déjà utilisé (CLI lancée en parallèle) | Choisir le bon port dans les options de l'intégration ; arrêter la CLI |
| `scan` trouve 0 carte | Croisement TX/RX, mauvais port | Voir [`../GUIDE.md`](../GUIDE.md) §6 (inverser paires 1-2 ↔ 4-5 côté adaptateur) |
| Carte « hors ligne » au milieu de la ligne | Trou dans le bus : le scan s'arrête au 1er silence | Renseigner « nombre de SPOT attendus » dans les options de l'intégration |
| Changements perdus après coupure de courant | `@SP` volatile, pas de `@WP` | Bouton « Sauvegarder NVM », ou option `save: true` des services |
| NAK 5 (checksum) | Parasites, bus long non terminé | Terminaison 100 Ω en bout de ligne (GUIDE racine §1.2) |
| Conteneur Docker : port absent | `--device` manquant | Relancer avec `--device /dev/ttyUSB0:/dev/ttyUSB0` ; rendre le port stable par règle udev (ID_SERIAL FTDI) |
| Lenteurs d'affichage | Polling trop fréquent | Augmenter l'intervalle de rafraîchissement dans les options (max 60 s) |
| Pas de `/dev/cu.usbserial-*` sur le Mac (macOS ≥ 26.6) | Pilote FTDI VCP non installé ou extension non validée | Installer le pilote VCP (ftdichip.com) + valider dans *Réglages Système → Confidentialité et sécurité*, redémarrer (`../README.md` §7.2) |
| Mauvais nom de port sur Mac | `tty.` au lieu de `cu.` | Utiliser `/dev/cu.usbserial-XXXX` (préfixe `cu.`) |
| `hass` refuse de démarrer sur le Mac | Python < 3.14.2 ou lancement hors venv (HA 2026.11) | Lancer via le venv uv 3.14 : `.venv-ha/bin/hass -c ~/.hass_dev` (§3.4) |
| Port série absent dans un conteneur sur Mac | Pas de passthrough USB fiable sur Docker Desktop / `container` macOS | Sur Mac, développer en venv `hass -c` (§3.4) ; réserver Docker au PC Linux cible ou aux tests pty |

Rendre le port série stable (udev) :

```sh
# /etc/udev/rules.d/99-phs16.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="phs16bus"
# → le port apparaîtra toujours comme /dev/phs16bus
```

---

## 7. Mise à jour de l'intégration

- **Copie manuelle** : recopier `custom_components/phs16lc/` (version plus
  récente) puis redémarrer HA.
- **Dépôt privé (Marketplace)** : l'entité « update » de `phs16lc` apparaît dans
  Réglages → Mises à jour ; un « repair » proposera le redémarrage.

## 8. Limites connues (à date de la v0.2)

- Le protocole PHS16-LC ne pousse pas d'état : l'affichage reflète un polling
  (10 s par défaut) — une commande manuelle externe (CLI) n'est visible qu'au
  prochain rafraîchissement.
- Une entité `light` = intensité **uniforme** sur les 16 canaux ; les réglages
  par groupe passent par les listes « Recette/Groupe » ou les services.
- Un seul bus (un port série) par instance de l'intégration ; plusieurs bus
  = plusieurs entrées de configuration (prévu, à confirmer en phase 1).
- L'instance HA tournant en venv sur le MacBook Pro (§3.4) est un environnement
  de **développement** : la production tourne sur le PC Linux dédié (§4).
