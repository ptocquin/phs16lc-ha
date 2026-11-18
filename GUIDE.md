# GUIDE — Intégration Home Assistant `phs16lc`

Choix du matériel, installation (hardware + software) et utilisation de
l'intégration Home Assistant qui pilote les luminaires **PHS16-LC** à distance.

> **Document vivant** — mis à jour au fur et à mesure du développement.
> Version : 0.43 — 2026-11-18 — **groupes de luminaires** (v1.3.0) : `groups.json`
> embarqué + copie auto au 1er boot, entités par groupe (light/select/bouton),
> services `address: "group:<id>"`, labels HA colorés + areas auto posés sur les
> devices membres (badges natifs), §6.8 ; §5.4 : recettes/scènes embarquées et
> copiées auto (si absentes) vers `<config>/phs16lc/` → boutons « Scène » visibles
> d'emblée ; générateur de dashboards lit `groups.json` (`--groups`) ; blueprint
> « recette planifiée d'un groupe » ; 96 tests OK.
> Version : 0.42 — 2026-11-18 — §5.4 : recettes/scènes NON embarquées dans
> l'intégration → copie obligatoire dans `<config>/phs16lc/{recipes,scenes}` ;
> HA OS 16+ monte la config en `/homeassistant` dans les add-ons (core toujours
> `/config`) → résolution automatique `/config` ↔ `/homeassistant` dans le code,
> warning au démarrage si dossier absent, et `recipes_dir` (configuré/résolu,
> nb de fichiers) exposé dans les diagnostics.
> Version : 0.41 — 2026-11-18 — mode boîtier dual (2× USB-RS485-WE) documenté :
> §1/§2.2 deux montages (USB-RS422-WE seul + alim externe, ou boîtier dual TX/RX
> avec alim 12–24 V intégrée), §3 CLI `--rx-port` / champ « Port série RX »,
> §4–§5 déploiement (udev double, `--device` ×2 en conteneur), §7 dépannage
> (alim 12–24 V sur pins 3/6=+, 4/5=masse, ordre TX/RX, paires 1-2 ↔ 7-8).
> Version : 0.40 — 2026-11-13 — §4.2.1 : DHCP encore en 10.18.x + ARP 10.16.52.1
> INCOMPLETE = le port switch n'est PAS encore sur le VLAN 10.16.52 → vérifier la
> prise physique (scv-pvg-svr06) et demander à l'IT de confirmer l'activation ;
> la config statique du Pi (10.16.52.22/24) est correcte, en attente du VLAN.
> Version : 0.39 — 2026-11-13 — §4.2.1 : ping gateway KO → vérifier la prise physique,
> tester le DHCP sur la prise (réservation 10.16.52.22 ?), `ip neigh` (ARP),
> `nslookup ghcr.io 139.165.214.214` (DNS direct, hors resolv.conf).
> Version : 0.38 — 2026-11-13 — §4.2.1 : cas « prise dédiée IT » (VLAN 10.16.52.0/24,
> IP statique 10.16.52.22, gateway/DNS fournis, firewall TCP 22/80/443/8123 ouvert
> depuis plages postes/VPN) — procédure de reconfiguration filaire simple.
> Version : 0.37 — 2026-11-13 — §4.2.2 : hotspot « IP configuration could not be
> reserved » → dnsmasq absent (mode shared) et/ou wlan0 encore en client → AP en
> ipv4.method manual 192.168.99.1/24, Mac en statique 192.168.99.2/24.
> Version : 0.36 — 2026-11-13 — §4.2.2 : sondes captive vides → d'abord vérifier
> association wlan0 (`nmcli device status`, `ip -4 addr show wlan0`, `ip route`) ;
> le portail est souvent servi par la gateway : `curl -s http://<gw>/`.
> Version : 0.35 — 2026-11-13 — §4.2.2 : SSID Guest ouvert (security « -- ») =
> portail captif → `nmcli device wifi connect "Guest"`, détecter le portail
> (captive.apple.com → Location), poster les credentials au formulaire, vérifier
> ghcr.io ; déconnecter enu1u1u1 pendant l'update (route par défaut via wlan0).
> Version : 0.34 — 2026-11-13 — §4.2.2 : Wi-Fi client sur le Pi = OK en WPA-PSK
> (SSID invité : `nmcli device wifi connect`), PAS en 802.1X entreprise (EAP non
> supporté par HA OS) ; le sous-réseau Wi-Fi a l'egress 443 → `ha core update` passe.
> Version : 0.33 — 2026-11-13 — §4.2.2 : partage Internet refusé (« protégée par
> 802.1X ») → partager depuis le VPN, ou NAT manuel Mac (sysctl forwarding + pfctl),
> ou allowlist IT 443 (pérenne).
> Version : 0.32 — 2026-11-13 — §4.2.x : « Can't update config on enu1u1u1 » → logs
> supervisor via `docker logs hassio_supervisor`, ou DNS en direct via nmcli
> (`ipv4.ignore-auto-dns yes ipv4.dns "1.1.1.1 8.8.8.8"`). Sur le LAN corporate le DNS
> marche déjà : le vrai blocage est l'egress 443 → sortir via le Mac ou allowlist IT.
> Version : 0.31 — 2026-11-13 — §4.2.x : `--ipv4-nameserver` prend UNE adresse par
> flag (erreur « expected IPv4Address » sinon) → répéter le flag, pas de virgule.
> Version : 0.30 — 2026-11-13 — §4.2.2 : aucun proxy (manuel ni PAC), Mac OK en 443
> depuis le Wi-Fi (curl ghcr.io → 405) mais Pi KO depuis 10.18.71.0/24 → faire
> sortir le Pi via le Mac (partage Internet) ou allowlist IT TCP/443 (pérenne).
> Version : 0.29 — 2026-11-13 — §4.2.2 : pas de proxy manuel sur le Mac → proxy auto
> PAC/WPAD (`networksetup -getautoproxyurl "Wi-Fi"`, lire le PAC pour extraire le
> PROXY) ; test `curl -sI https://ghcr.io` sur le Mac pour savoir si le Wi-Fi a l'egress 443.
> Version : 0.28 — 2026-11-13 — §4.2.2 : DNS OK mais curl https KO = egress TCP/443
> bloqué → proxy corporate (`networksetup -getsecurewebproxy` sur le Mac, test
> `curl -x` depuis le Pi, `ha network update enu1u1u1 --proxy …`) ou allowlist 443
> ghcr.io/github.com auprès de l'IT.
> Version : 0.27 — 2026-11-13 — §4.2.2 : « HomeAssistantCore.update blocked … no host
> internet connection » = check de connectivité du Supervisor KO → tester
> `curl -sI https://ghcr.io/v2/`, DNS public `--ipv4-nameserver 1.1.1.1`, ou proxy
> corporate (`--proxy` si supporté), puis `ha core update`.
> Version : 0.26 — 2026-11-13 — §4.2.2 : DNS OK mais téléchargement du core bloqué =
> egress HTTPS ghcr.io/github.com → tester `curl -sI https://ghcr.io`, proxy corporate
> (`networksetup -getsecurewebproxy`, `--proxy`), repli = câble corporate + `ha core update`.
> Version : 0.25 — 2026-11-13 — §4.2.2 : DNS 192.168.2.1 (partage macOS) inefficace →
> DNS explicite sur le Pi (`--ipv4-nameserver 1.1.1.1 --ipv4-nameserver 8.8.8.8` —
> une adresse par flag, pas de virgule — ou DNS corporate du
> Mac via `scutil --dns`) ; si ghcr.io bloqué → câble corporate pour le download.
> Version : 0.24 — 2026-11-13 — §4.2.2 : `ipv4-method auto` sans IP = pas de serveur
> DHCP sur le lien direct → activer le partage Internet du Mac (192.168.2.1), ou
> statique 192.168.2.10/24 gw/DNS 192.168.2.1 ; `nmcli device connect enu1u1u1`.
> Version : 0.23 — 2026-11-13 — §4.2.2 : piège « Problème de réseau détecté / pas
> d'interface primaire » en lien direct sans gateway → partage Internet du Mac
> (192.168.2.1) + DHCP, ou statique avec gateway+DNS.
> Version : 0.22 — 2026-11-13 — §4.2.1/§4.2.2 : sur Pi 3B+ l'Ethernet s'appelle
> `enu1u1u1` (puce USB LAN7515), pas `eth0` (Pi 4/5) — commandes corrigées.
> Version : 0.21 — 2026-11-13 — §4.2.2 : connexion directe au Pi quand le LAN filtre
> (câble Ethernet direct + IP statiques ; hotspot Wi-Fi AP via nmcli sur wlan0).
> Version : 0.20 — 2026-11-13 — §4.2.1 : `docker exec` dans l'image HA → chemins
> absolus (`/bin/sh -c …`, PATH de l'image sans /bin) ; ou éditer directement
> côté hôte `/mnt/data/supervisor/homeassistant` (même bind mount que /config).
> Version : 0.19 — 2026-11-13 — §4.2.1 : répertoire vide + conteneur running =
> onboarding non fait → créer configuration.yaml soi-même ; `docker exec … sh -c`
> (PATH minimal de l'image HA) ; `mount | grep` vide = normal.
> Version : 0.18 — 2026-11-13 — §4.2.1 : répertoire homeassistant vide → vérifier
> `docker ps` / bind mount réel (`docker inspect … /config`, `mount`), écrire au
> besoin via `docker exec -i homeassistant tee /config/configuration.yaml`.
> Version : 0.17 — 2026-11-13 — §4.2.1 : changer le port de HA, procédure exacte
> (chemin réel `/mnt/data/supervisor/homeassistant/configuration.yaml`, `http:
> server_port`, validation YAML via le conteneur, `ha core restart`).
> Version : 0.16 — 2026-11-13 — §4.2.1 : cas constaté « ping OK mais TCP/8123 timeout » =
> DROP inter-VLAN (Mac Wi-Fi 10.22.x vs Pi 10.18.x) → filaire même VLAN, VPN, ou ACL IT.
> Version : 0.15 — 2026-11-13 — §4.2.1 : clavier AZERTY à la console (SSH depuis le
> Mac recommandé ; à défaut `loadkeys fr` ou keymap minimal lettres-seules).
> Version : 0.14 — 2026-11-13 — §7 : ligne de dépannage « curl → 000 depuis le LAN »
> (arbre de diagnostic IP/écoute/route/ACL/VPN/isolement Wi-Fi).
> Version : 0.13 — 2026-11-13 — §4.2.1 : depuis `ha>`, la commande `login` ouvre un
> shell bash root (`exit` pour revenir).
> Version : 0.12 — 2026-11-13 — §4.2.1 : port 8123 filtré par le réseau d'entreprise
> (test local/LAN, demande d'ACL à l'IT, repli tunnel SSH, changement de port).
> Version : 0.11 — 2026-11-13 — §4.2.1 : réseau après le 1er boot HA OS (DHCP auto sur
> eth0, `ha network info`, `homeassistant.local` souvent filtré en entreprise, IP fixe
> en option, proxy pour les add-ons).
> Version : 0.10 — 2026-11-13 — §4.1 : pièges boot USB documentés (`tee -a` et non `tee`,
> `config.txt` et non `userconfig.txt`, switch LOCK de la SD, test « SSD seul » d'abord,
> `remount rw /boot` sous HA OS).
> Version : 0.9 — 2026-11-13 — §4.1 : image « Raspberry Pi 3 64-bit » (HA OS 18.5)
> confirmée présente dans Raspberry Pi Imager v2.0.12 ; le repli conteneur (§5.2)
> reste documenté par précaution.
> Version : 0.8 — 2026-11-13 — ajout du §4 « Raspberry Pi 3B+ (tests préliminaires) »
> (boot USB SSD, recorder allégé, limites 1 Go RAM) ; renumérotation : l'ancien §4
> (déploiement PC Linux) devient §5, puis §5→§6, §6→§7, §7→§8, §8→§9.
> Version : 0.7 — 2026-11-12 — §4.3 méthode 2 détaillée : `git subtree push --prefix=ha-integration` vers un dépôt GitHub dédié, installable via le Marketplace intégré.
> Version : 0.6 — 2026-11-11 — outils de déploiement documentés (§4.3 : package_release.py + deploy_to_linux.sh).
> Version : 0.5 — 2026-11-11 — procédure E2E sans matériel (fake_spot + API REST) validée et documentée (§3.4.1).
> Version : 0.4 — 2026-11-11 — benchmark mini-PC N100 et shortlist documentés (§2.1).
> Version : 0.3 — 2026-11-11 — question « Mac mini refurbished ? » tranchée et
> documentée (§2.1.1) : machine dédiée = PC Linux, Mac réservé au développement.
> Version : 0.2 — 2026-11-11 — ajout du développement/test local sur MacBook Pro (§3)
> et de la procédure de déploiement sur le PC Linux dédié (§4).
> Version : 0.1 — 2026-11-11 — état : installation/usage prévus, intégration en
> cours de développement (voir [`PLAN.md`](PLAN.md)).
> Le protocole et le câblage du bus sont détaillés dans [`../GUIDE.md`](../GUIDE.md)
> (adaptateur USB-RS422-WE seul, ou boîtier dual 2× USB-RS485-WE ; pinout RJ45
> + alim 12–24 V ; sertissage) et [`../README.md`](../README.md).

---

## 1. Vue d'ensemble

L'intégration `phs16lc` fait le lien entre Home Assistant et le bus RS-485
des luminaires PHS16-LC :

```
Appli mobile / navigateur ──► Home Assistant ──► intégration phs16lc ──► port TX (/dev/ttyUSB0)
                                                                    │  (pyserial, cœur = phs16ctl)
                                                                    │  boîtier dual : + port RX (/dev/ttyUSB1)
                                                                    ▼
              ┌─ montage A : 1× FTDI USB-RS422-WE (full duplex) + alim 12–24 V externe
              └─ montage B : boîtier fabricant 2× USB-RS485-WE (TX + RX), alim 12–24 V intégrée
                                                                    │
                                                                    ▼
                                              bus RS-485 sur RJ45 ──► SPOT 1..N
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
au §5 — aucun changement de code entre les deux (voir PLAN D18).

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
rempli par le MacBook Pro (§3). Le déploiement cible reste un PC Linux (§5).

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

### 2.2 Câblage du bus (RJ45 + alim 12–24 V) et adaptateur(s) USB

**Pinout RJ45 du bus** (confirmé par le concepteur P. Jenard, email du
2026-11-18 — détail et sertissage dans [`../GUIDE.md`](../GUIDE.md) §1.2) :

| Pins RJ45 | Signal |
| --- | --- |
| 1-2 (paire orange) | RS-485 montante : données **PC → SPOT** (A+ / B−) |
| 7-8 (paire marron) | RS-485 descendante : réponses **SPOT → PC** (A+ / B−) |
| 3 et 6 (paire verte) | **+12..24 V** (alimentation de la ligne série) |
| 4 et 5 (paire bleue) | **masse** de cette alimentation |

L'**alimentation 12–24 V sur le RJ45 est obligatoire** : l'alim des LED est
isolée galvaniquement de celle de la ligne série, et l'interface de
communication du luminaire est alimentée par le bus. Sans elle, le luminaire
ne répond à rien (scan vide).

Deux montages possibles côté PC :

| | **Montage A — un seul adaptateur** | **Montage B — boîtier dual du fabricant** |
| --- | --- | --- |
| Matériel | 1× **FTDI USB-RS422-WE-1800-BT** (full duplex 4 fils, datasheet `../0900766b80da71a2.pdf`) | 2× **FTDI USB-RS485-WE-1800-BT** (half duplex) + boîtier d'interface du fabricant (schéma fourni par email le 2026-11-18 ; soft de référence : `light-monitor-dual/`) |
| Câblage | fils nus sur RJ45 : orange=TXD+→pin 1, rouge=TXD−→pin 2, jaune=RXD+→pin 7, blanc=RXD−→pin 8, noir=GND→pins 4/5 | câble **TX** : orange (Data+ A)→pin 1, jaune (Data− B)→pin 2 ; câble **RX** : orange→pin 7, jaune→pin 8 |
| Alimentation | alim **externe 12–24 V** : + → pins 3/6, − → pins 4/5 | injectée **par le boîtier** (+ pins 3/6, masse 4/5) |
| Ports série vus | **1** (`/dev/ttyUSB0`, `/dev/cu.usbserial-XXXX`) | **2** : TX et RX (un par câble) |
| Config HA | champ « Port série » seul | « Port série » = TX, **« Port série RX »** = RX |
| CLI | `phs16ctl --port P …` | `phs16ctl --port P_TX --rx-port P_RX …` |

> Ne **pas** utiliser un seul câble USB-RS485-WE (half duplex 2 fils) : il
> faut soit le USB-RS422-WE (montage A), soit **deux** USB-RS485-WE via le
> boîtier (montage B).

| Élément | Détail |
| --- | --- |
| Côté PC (Linux) | `/dev/ttyUSB0`, pilote noyau `ftdi_sio` inclus, rien à installer ; port rendu stable par udev (§7) |
| Côté PC (macOS) | pilote FTDI VCP à installer (§3.1) → `/dev/cu.usbserial-XXXX` (préfixe `cu.`) |
| Détection | `ls /dev/ttyUSB*` / `ls /dev/cu.usbserial*`, ou la liste proposée dans le formulaire de configuration |

Câblage du bus (pinout RJ45 T568B, sertissage, terminaison 100 Ω, topologie
linéaire) : voir [`../GUIDE.md`](../GUIDE.md) §1.2 — ne pas réinventer ici.

### 2.3 Récapitulatif du matériel à acheter

- [ ] Mini-PC N100 16 Go + SSD 256 Go (ou Raspberry Pi 5 8 Go + SSD USB/NVMe)
- [ ] SSD USB 120 Go+ pour le **Pi 3B+ de tests préliminaires** (§4) — le Pi 3B+ lui-même est déjà en stock
- [ ] Câble Ethernet (branchement au réseau entreprise)
- [ ] **Montage A** : adaptateur **FTDI USB-RS422-WE-1800-BT** (full duplex, 1 port) + **alim externe 12–24 V** — **OU** **montage B** : boîtier fabricant avec **2× USB-RS485-WE-1800-BT** (2 ports TX + RX, alim 12–24 V intégrée au boîtier)
- [ ] Câble bus Cat5e/Cat6a/Cat7 + connecteurs RJ45 blindés (voir GUIDE racine §1.2)
- [ ] Alimentation **12–24 V sur le bus RJ45** (pins 3/6 = +, 4/5 = masse). **Obligatoire** : sans elle, l'interface série du luminaire est muette (scan vide). En montage A, alim externe ; en montage B, fournie par le boîtier
- [ ] (Optionnel) petit onduleur (UPS) pour éviter les coupures de courant

---

## 3. Développement et tests locaux sur MacBook Pro (cette machine)

Tout le développement se fait sur ce MacBook Pro (macOS 26.6.2, Apple Silicon),
y compris avec les **vrais luminaires branchés en USB**. Le déploiement final sur
le PC Linux est décrit au §5 : **aucun changement de code** n'est nécessaire
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
  En montage boîtier dual, **deux** ports apparaissent (un par câble
  USB-RS485-WE) : repérer lequel est le TX via `ls -l /dev/serial/by-id/`
  (le nom contient le n° de série du câble, câblé sur les pins 1-2).
- Brancher l'adaptateur (USB-RS422-WE, ou les deux câbles du boîtier dual) et
  le bus des luminaires (câblage : §2.2 et `../GUIDE.md` §1.2).

### 3.2 Tester le backend `phs16ctl` seul (sans Home Assistant)

```sh
cd phs16ctl
uv sync
uv run pytest                                        # tests unitaires (FakeLink, sans matériel)
uv run phs16ctl --list-ports                         # doit lister /dev/cu.usbserial-XXXX
uv run phs16ctl --port /dev/cu.usbserial-XXXX scan   # vrais luminaires
uv run phs16ctl --port /dev/cu.usbserial-XXXX on 1 800
uv run phs16ctl --port /dev/cu.usbserial-XXXX status 1
# carte programmée à une adresse > 1 (l'adresse 1 est muette) :
uv run phs16ctl --port /dev/cu.usbserial-XXXX scan --expected 33
# boîtier dual (2 ports : TX + RX) :
uv run phs16ctl --port /dev/cu.usbserial-TX --rx-port /dev/cu.usbserial-RX scan --expected 33
```

Sans luminaire (simulateur sur port pty) :

```sh
# --duration long indispensable : 120 s par défaut, le simulateur meurt en pleine session
python3 ../light-monitor/tools/fake_spot.py --boards 3 --duration 86400 > /tmp/port.txt 2>/tmp/trames.log &
sleep 1
cd phs16ctl && uv run phs16ctl --port "$(cat /tmp/port.txt)" scan
# trames échangées (avec checksum vérifié) dans /tmp/trames.log
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
  avec le port `/dev/cu.usbserial-XXXX`. En boîtier dual, renseigner aussi
  **« Port série RX »** avec le second port.
- Le symlink rend le code du dépôt **live** : après chaque modification,
  redémarrer `hass` (Ctrl-C puis relancer) pour recharger l'intégration.
- **Pourquoi pas de conteneur sur le Mac** : le passthrough USB des ports série
  vers un conteneur (Docker Desktop, ou `container` d'Apple sur macOS 26) reste
  fragile ; le venv accède directement à `/dev/cu.usbserial-XXXX`. Sur le Mac,
  Docker ne sert que pour des tests sans matériel (port pty).

#### 3.4.1 Scénario E2E complet sans matériel (validé le 2026-11-11)

Simulateur + HA local + pilotage par API REST — permet de valider toute la chaîne
(backend `phs16ctl`, coordinator, entités, services, événements) sans luminaire :

```sh
# 1. Simulateur 3 SPOT / 16 canaux sur un pty (--duration long ! défaut 120 s)
ha-integration/.venv-ha/bin/python light-monitor/tools/fake_spot.py \
    --boards 3 --channels 16 --duration 86400 > /tmp/phs_port.txt 2> /tmp/phs_trames.log &

# 2. Chemin STABLE pour le pty : macOS renumérote le pty à chaque lancement
#    (ttys011 → ttys013…), donc on fixe un symlink que l'entrée HA retiendra
ln -sf "$(cat /tmp/phs_port.txt)" /tmp/phs_pty

# 3. HA local (voir §3.4)
ha-integration/.venv-ha/bin/hass -c ~/.hass_dev     # → http://localhost:8123

# 4. Onboarding par API (premier lancement uniquement) :
curl -s -X POST http://localhost:8123/api/onboarding/users \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"http://localhost:8123/","name":"Dev","username":"dev","password":"…","language":"fr"}'
#    → {"auth_code":"…"} puis ATTENTION : /auth/token (pas /api/auth/token) :
curl -s -X POST http://localhost:8123/auth/token \
  -d 'grant_type=authorization_code&code=<auth_code>&client_id=http://localhost:8123/'
#    → {"access_token":"…"} : Bearer pour tous les appels suivants

# 5. Config flow par API (remplacer <flow_id>) :
curl -s -X POST http://localhost:8123/api/config/config_entries/flow \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"handler":"phs16lc","show_system_options":true}'
curl -s -X POST http://localhost:8123/api/config/config_entries/flow/<flow_id> \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"port":"/tmp/phs_pty","expected_spots":3,"poll_interval":5,"recipes_dir":"/Users/ptocquin/.hass_dev/phs16lc/recipes"}'
#    → create_entry avec state "loaded"
#    (champ "rx_port" optionnel : vide = mono-port ; pour tester le mode dual
#     sans matériel, light-monitor-dual/tools/fake_spot.py --split fournit DEUX pty)

# 6. Scénario E2E (exemples) :
curl -s -X POST http://localhost:8123/api/services/light/turn_on \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"entity_id":"light.spot_1","brightness":200}'          # → @SP 0x1 1702×16
curl -s -X POST http://localhost:8123/api/services/select/select_option \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"entity_id":"select.spot_1_recipe","option":"croissance.json"}'
curl -s -X POST http://localhost:8123/api/services/button/press \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"entity_id":"button.phs16_lc_tmp_phs_pty_serre"}'       # scène multi-cartes
curl -s -X POST http://localhost:8123/api/services/phs16lc/save \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"address":"1"}'
curl -s -X POST http://localhost:8123/api/services/phs16lc/scan -H "Authorization: Bearer $TOKEN"

# 7. Vérifications :
#    - états :            GET /api/states
#    - trames série :     /tmp/phs_trames.log (@SP/@WP/@GI/@GT avec checksum)
#    - événements HA :    table `events` du recorder ~/.hass_dev/home-assistant_v2.db
#                      (event_type LIKE 'phs16lc%') → visibles aussi dans le logbook
```

Résultat obtenu le 2026-11-11 : 46 entités (3 `light.spot_N`, 6 `select`, 4 `button`,
10 `sensor`, 3 `binary_sensor`), mapping luminosité→mA vérifié (brightness 200 →
1702 mA, 128 → 1116 mA), scène `serre.json` appliquée correctement (groupe partiel
`500×8 + 1200×8` sur le SPOT 2 ; carte 4 absente du bus simulé = erreur comptée,
sans plantage), événements `phs16lc_recipe_applied/scene_applied/saved/scan`
persistés par le recorder.

> **Pièges rencontrés (2026-11-11)** :
> - `fake_spot.py` a un `--duration` de **120 s par défaut** : sans `--duration` long,
>   le simulateur s'arrête au milieu du scan → `SerialException` côté HA.
> - Le pty change de nom à chaque lancement du simulateur → utiliser un **symlink
>   stable** (`/tmp/phs_pty`) comme port dans l'entrée HA.
> - Après une modification du code de l'intégration, **redémarrer le processus
>   `hass`** : recharger l'entrée (API `…/reload`) ne réimporte pas les modules Python.
> - Jeton API : endpoint `POST /auth/token` (sans préfixe `/api`).
> - HA 2026.11 : `DeviceInfo.via_device` est déprécié (suppression 2027.8) et
>   provoquait « Error adding entity None » sur les entités des SPOT ajoutés hors
>   du setup initial → l'intégration crée le device hub (`ensure_hub_device`) et
>   référence les SPOT via `via_device_id` (D19, test de régression en place).

### 3.5 Checklist de validation avec les vrais luminaires (sur le Mac)

- [ ] Scan : toutes les cartes apparaissent (« SPOT 1 », « SPOT 2 »…) avec le capteur « en ligne ».
- [ ] On/off + luminosité depuis le tableau de bord → les vraies LED réagissent ; le mA lu correspond au curseur.
- [ ] Recette complète, puis groupe partiel (listes déroulantes « Recette » / « Groupe »).
- [ ] Scène multi-cartes (bouton « Scène … »).
- [ ] « Sauvegarder NVM » puis coupure de l'alimentation d'un luminaire → les courants sont conservés au redémarrage.
- [ ] Températures remontées et historisées (barre latérale « Historique ») ; alerte > 70 °C testée.
- [ ] Carte éteinte au milieu du bus → signalée « hors ligne » grâce au réglage « nombre de SPOT attendus ».

---

## 4. Installation sur Raspberry Pi 3B+ (tests préliminaires)

Les Pi 3B+ en stock (Cortex-A53, **1 Go de RAM**) ne remplacent pas la machine
dédiée du §5, mais ils permettent de **valider toute la chaîne de bout en bout**
avant l'achat du mini-PC : HA OS, installation de l'intégration `phs16lc`,
adaptateur USB-RS422, vrais luminaires, accès VPN. Aucun changement de code par
rapport à la cible finale — seul le matériel diffère.

### 4.1 Image et stockage : les deux points bloquants

| Élément | Recommandation | Pourquoi |
| --- | --- | --- |
| Image HA OS | « **Raspberry Pi 3 64-bit** » — **HA OS 18.5**, proposée directement dans **Raspberry Pi Imager v2.0.12** (vérifié le 2026-11-13), ou sur <https://www.home-assistant.io/installation/raspberrypi> | L'image 32-bit n'est plus maintenue. Si le Pi 3 venait à être retiré des images officielles, repli = Raspberry Pi OS Lite 64-bit + conteneur HA (méthode du §5.2) |
| Stockage | **SSD sur port USB** (boot USB), jamais de carte SD en continu | Le recorder HA écrit en permanence : une SD s'userait en quelques semaines. Le boot USB 2.0 du 3B+ (~35 Mo/s réels) suffit largement |
| Alimentation | Alimentation officielle **5 V / 2,5 A** | Sous-alimentation = undervoltage et instabilité du port USB, donc du bus RS-422 |
| Réseau | **Ethernet**, pas de Wi-Fi pendant les tests | Fiabilité |

Activer le boot USB sur le Pi 3B+ (une seule fois ; les unités récentes l'ont
souvent déjà en sortie d'usine) :

```sh
# Depuis une carte SD Raspberry Pi OS bootée sur le Pi : poser le bit de boot USB (OTP), booter une fois, retirer la SD
echo program_usb_boot_mode=1 | sudo tee -a /boot/firmware/config.txt   # Bookworm — APPEND (tee -a), ne pas écraser config.txt
# (firmware plus ancien : /boot/config.txt)
grep program_usb_boot_mode /boot/firmware/config.txt                    # vérifier que la ligne est bien là
sudo reboot   # attendre ~10 s, éteindre, retirer la SD
```

> **Pièges boot USB (constatés le 2026-11-13)** :
> - Ne **pas** créer `userconfig.txt` : le firmware ne lit que `config.txt` → écrire
>   directement dans `config.txt` (`tee -a /Volumes/system-boot/config.txt` depuis le
>   Mac, `/boot/firmware/config.txt` sur le Pi en Bookworm).
> - « Read-only file system » depuis le Mac = **switch LOCK de l'adaptateur SD en
>   position verrouillée** : `diskutil info /Volumes/system-boot` affiche alors
>   « Media Read-Only: Yes » (et « Volume Read-Only: Yes (read-only mount flag set) »).
>   Aucun remount rw ne fonctionne tant que le verrou hardware est actif → éjecter la
>   carte, glisser le switch sur déverrouillé, réinsérer, puis vérifier que
>   « Media Read-Only » passe à « No » et remonter :
>   `diskutil unmount /Volumes/system-boot && diskutil mount /Volumes/system-boot`
>   (ou `sudo mount -uw /dev/disk13s1` — sur macOS le remount prend le **nœud
>   périphérique**, pas le point de montage ; « invalid special file » sinon).
>   Si le switch est cassé : changer d'adaptateur/carte, ou tester d'abord le
>   boot « SSD seul » (bit OTP déjà posé).
> - **Tester d'abord si le bit OTP n'est pas déjà posé** (unités 3B+ récentes) : flasher
>   HA OS sur le SSD USB, ne brancher **que** le SSD sur le Pi et alimenter — si HA
>   démarre, le boot USB est déjà actif, aucune SD nécessaire. Contrôle explicite sur
>   le Pi : `vcgencmd otp_dump`.
> - Sur le Pi booté depuis la SD, `/boot/firmware` est monté rw (Bookworm) ; sous
>   **HA OS** `/boot` est monté ro → `sudo mount -o remount,rw /boot` avant d'éditer.

Puis flasher l'image HA OS **directement sur le SSD USB** — dans Raspberry Pi
Imager v2.0.12 : *Home Assistant OS → Raspberry Pi 3 64-bit (HA OS 18.5)* — ou
avec Balena Etcher / `dd` — et démarrer avec SSD + Ethernet + adaptateur
USB-RS422-WE (ou les deux câbles du boîtier dual) branchés.

### 4.2 Premier démarrage et installation de l'intégration

1. Premier boot : compter **15–25 min** (nettement plus lent qu'un Pi 5 ou un
   N100), puis ouvrir `http://homeassistant.local:8123` et faire l'onboarding
   (compte administrateur).
2. Installer l'add-on **Terminal & SSH** (Boutique) pour le dépannage.
3. Rendre le(s) port(s) série stable(s) (sinon `/dev/ttyUSB0` peut devenir
   `ttyUSB1` après un reboot) : règle udev du **§7** → `/dev/phs16bus`, plus
   `/dev/phs16rx` en boîtier dual (deux câbles FTDI = deux ports).
4. Déployer l'intégration exactement comme sur la cible finale : les méthodes du
   **§5.3** s'appliquent telles quelles (un Pi en HA OS a aussi un `/config`) :

   ```sh
   # Depuis le Mac de développement :
   ha-integration/tools/deploy_to_linux.sh pi@192.168.1.60     # HA OS : /config par défaut
   ```

   puis redémarrer HA (Réglages → Système → Redémarrer).
5. Ajouter l'intégration **PHS16-LC** (Réglages → Appareils et services) avec le
   port `/dev/phs16bus`, le nombre de SPOT attendus, l'intervalle de
   rafraîchissement et le dossier des recettes `/config/phs16lc/recipes`
   (copier les JSON de `phs16ctl/recipes/` et `phs16ctl/scenes/`, voir §5.4).
   En boîtier dual, renseigner en plus **« Port série RX » = `/dev/phs16rx`**.

#### 4.2.1 Réseau après le premier boot (réseau d'entreprise en DHCP)

Dès le premier boot, HA OS tente **DHCP automatiquement sur Ethernet** : rien à
configurer si le câble est branché. Depuis la console (login `root`, pas de mot de
passe avant l'onboarding → invite `ha>`) :

```sh
ha network info        # interfaces : l'Ethernet + wlan0 (Wi-Fi), avec IP/gateway/DNS
```

> Sur Pi 3B+, l'interface Ethernet s'appelle **`enu1u1u1`** (Ethernet via la puce
> USB LAN7515), pas `eth0` (nom `eth0` sur Pi 4/5) — utiliser `enu1u1u1` dans toutes
> les commandes `ha network update …` ci-dessous.

- Depuis l'invite `ha>` de la console, la commande **`login`** ouvre un shell
  **bash root** (`exit` pour revenir à `ha>`) — utile pour `docker ps`, éditer
  `/boot/config.txt` (`mount -o remount,rw /boot` d'abord, monté ro), etc.
- **Clavier AZERTY à la console physique** : pas de réglage natif sur HA OS (pas
  de systemd/localectl). Le plus confortable : **SSH depuis le Mac** (add-on
  Terminal & SSH) — le layout est géré par macOS. À la console, en dernier
  recours : `loadkeys fr` si binaire + keymaps présents, sinon keymap minimal
  « lettres seules » (les chiffres restent en direct, pratiques pour les IP) —
  non persistant, perdu au reboot :

  ```sh
  printf 'keycode 16 = a\nkeycode 17 = z\nkeycode 30 = q\nkeycode 44 = w\nkeycode 39 = m\nkeycode 40 = ugrave\nkeycode 50 = comma\nkeycode 51 = semicolon\nkeycode 52 = colon\nkeycode 53 = exclam\n' > /tmp/azerty.map
  loadkeys /tmp/azerty.map
  ```
- Ouvrir l'interface web depuis un poste du même réseau : `http://<ip>:8123` →
  onboarding. **`homeassistant.local` ne résout souvent pas sur un LAN
  d'entreprise** (mDNS filtré) : utiliser l'IP affichée par `ha network info`.
- **IP fixe** (recommandé à terme — « IP fixe ou DHCP réservé conseillé », §2.1) :

  ```sh
  ha network update enu1u1u1 --ipv4-method static \
    --ipv4-address 192.168.1.60/24 --ipv4-gateway 192.168.1.1 \
    --ipv4-nameserver 192.168.1.1 --ipv4-nameserver 1.1.1.1   # une adresse par flag !
  ```

  À faire **depuis la console**, pas depuis une session SSH (on perdrait la
  connexion). Valeurs acceptées par `--ipv4-method` selon version : `auto` (DHCP,
  défaut) / `static` (ou `manual`) — `ha network update enu1u1u1 --help` tranche.
  Pour le Pi de test, le DHCP suffit ; en production, préférer une réservation DHCP
  côté serveur d'entreprise.
- **Cas « prise dédiée IT » (2026-11-13)** : prise Ethernet reconfigurée sur un VLAN
  dédié (10.16.52.0/24), IP statique fournie, firewall ouvert (TCP 22/80/443/8123
  depuis les plages postes/VPN vers l'IP du Pi) :

  ```sh
  ha network update enu1u1u1 --ipv4-method static \
    --ipv4-address 10.16.52.22/24 --ipv4-gateway 10.16.52.1 \
    --ipv4-nameserver 139.165.214.214 --ipv4-nameserver 139.165.214.215
  # si « Can't update config on enu1u1u1 » → nmcli direct (voir §4.2.2)
  ha network info                        # IP, gateway, DNS, interface primaire
  nslookup ghcr.io
  curl -sI --max-time 8 https://ghcr.io/v2/ | head -1
  ha core update                         # egress via la gateway du VLAN dédié
  nmcli radio wifi off                   # couper le Wi-Fi : filaire seul
  ```

  Depuis un poste autorisé : `nc -zv 10.16.52.22 80` puis `http://10.16.52.22/`
  (8123 aussi ouvert). Nom d'hôte si IT a réservé un nom pour la prise :
  `ha hostname scv-pvg-svr06`.
  Si `ping 10.16.52.1` / `nslookup` KO alors que l'IP est bonne : vérifier la prise
  physique (scv-pvg-svr06), tester le DHCP sur la prise
  (`ha network update enu1u1u1 --ipv4-method auto` → quelle IP est attribuée ?
  souvent une réservation existe pour l'IP fournie), `ip neigh` (l'ARP de la
  gateway est-il résolu ?), et tester le DNS en direct
  (`nslookup ghcr.io 139.165.214.214`) pour séparer DNS de routage.
  Constaté le 2026-11-13 : DHCP toujours en 10.18.x + `ip neigh` → `10.16.52.1
  INCOMPLETE` = **le port switch n'est pas encore passé sur le VLAN 10.16.52**
  (pas un problème de config du Pi). Actions : vérifier que le câble est bien sur
  la prise **scv-pvg-svr06**, demander à l'IT de confirmer que la config du port
  est appliquée (et si 10.16.52.22 est une réservation DHCP ou à poser en
  statique), puis retester le DHCP sur la bonne prise → 10.16.52.x attendu.
- Nom d'hôte optionnel : `ha hostname phs16-pi-test`.
- **Accès Internet / add-ons** : installer l'add-on Terminal & SSH (étape 2)
  exige que le Supervisor joigne Internet. Si le réseau d'entreprise filtre les
  sorties, configurer le proxy de HA OS (option proxy de `ha network update enu1u1u1
  --help`) ou faire autoriser les domaines du store.
- **Port 8123 filtré par le réseau d'entreprise** : HA OS écoute sur 8123 sans
  pare-feu entrant — vérifier depuis le Pi que HA répond en local
  (`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8123` → 200/302), puis
  depuis un poste du LAN (`nc -zv <ip-du-pi> 8123`). Si le LAN bloque (ACL /
  isolement client), demander à l'IT : « autoriser en entrée **TCP/8123** sur
  `<ip-du-Pi>` depuis `<sous-réseau des postes / plage VPN>` ». Repli si refusé :
  tunnel SSH via l'add-on Terminal & SSH (le port 22 est souvent ouvert) :
  `ssh -N -L 8123:localhost:8123 root@<ip-du-pi>` puis `http://localhost:8123` ;
  cas constaté le 2026-11-13 : Mac en Wi-Fi sur un **autre sous-réseau** que le Pi
  (10.22.52.x vs 10.18.71.x) — ping OK (ICMP autorisé) mais TCP/8123 en timeout =
  DROP inter-VLAN. Solutions : se brancher **en filaire sur le même VLAN que le
  Pi** (`ipconfig getiflist` pour trouver l'interface — `en0` est le Wi-Fi), ou
  activer le VPN, ou demander l'ACL à l'IT ;
  ou changer le port de HA (`http: server_port: 80` dans `configuration.yaml`,
  redémarrer HA — non officiel sur HA OS mais fonctionnel). **Ne jamais exposer
  8123 sur Internet** : l'accès distant passe par le VPN (§5.6).

**Changer le port de HA (procédure exacte, constatée le 2026-11-13).** Sur HA OS,
le `configuration.yaml` n'est **pas** à la racine de l'hôte (c'est pourquoi
`find / -name configuration.yaml` ne retourne rien selon le shell utilisé) : la
racine hôte est un overlay read-only et la config vit sur la partition data,
montée dans le conteneur HA en `/config`. Depuis la **console hôte** (bash root)
elle est à `/mnt/data/supervisor/homeassistant/configuration.yaml`
(`find /mnt/data -name configuration.yaml`). Depuis l'add-on **Terminal & SSH**
(qui ne voit pas `/mnt/data`), passer par le conteneur :
`docker exec homeassistant cat /config/configuration.yaml`.

```sh
# console hôte (bash root) :
CFG=/mnt/data/supervisor/homeassistant/configuration.yaml
cp "$CFG" "$CFG.bak"
vi "$CFG"        # ajouter une section racine (ou compléter http: existant) :
#   http:
#     server_port: 80        # 80 si seuls les ports web passent entre VLANs, sinon 8124…
# valider le YAML AVANT de redémarrer (python dispo dans le conteneur HA) :
docker exec homeassistant python -c "import yaml; yaml.safe_load(open('/config/configuration.yaml'))"
ha core restart
ss -tlnp | grep -E ':(80|8124) '    # HA écoute sur le nouveau port
```

L'UI devient `http://<ip-du-pi>:<port>`. Revenir en arrière : restaurer le
`.bak`. Variante propre en UI : add-on **File editor** ou **Studio Code Server**
(montent `/config` correctement). Le conteneur HA tourne en réseau host sur HA OS,
donc `server_port` est bien pris en compte — mais ce réglage reste non officiel
sur HA OS (quelques liens internes supposent 8123).

> Si `/mnt/data/supervisor/homeassistant` apparaît **vide** : soit le conteneur HA
> n'est pas encore démarré (premier boot en cours — attendre, puis `docker ps`),
> soit le bind mount a une autre source. Vérifier la source réelle :
> `docker inspect homeassistant | grep -B3 -A6 '"/config"'` et
> `mount | grep -i homeassistant`, et lister le vrai contenu :
> `docker exec homeassistant ls -la /config`. Écrire au besoin **via le conteneur**
> (indépendant du chemin hôte) :
> `docker exec -i homeassistant tee /config/configuration.yaml >/dev/null <<'EOF'`
> puis coller le YAML `http: server_port: …`, `EOF`, et `ha core restart`.
> Constaté le 2026-11-13 : répertoire vide + conteneur `homeassistant` running =
> **onboarding jamais fait** (HA OS n'écrit `configuration.yaml` qu'à
> l'onboarding) → créer le fichier soi-même. `mount | grep homeassistant` vide =
> normal (bind mounts conteneur hors `/proc/mounts` hôte). `docker exec
> homeassistant ls …` échoue (« ls not found in $PATH », PATH minimal de l'image
> HA) → utiliser les chemins absolus dans le conteneur :
> `docker exec homeassistant /bin/sh -c 'ls -la /config'`
> (PATH de l'image HA sans `/bin` — le voir : `docker inspect homeassistant
> --format '{{.Config.Env}}'`), ou plus simple : éditer directement **côté hôte**
> `/mnt/data/supervisor/homeassistant/` — c'est le même bind mount que `/config`.

#### 4.2.2 Connexion directe au Pi (contourner un filtrage inter-VLAN)

Avant toute chose, vérifier que HA écoute bien sur le port visé côté Pi :
`ss -tlnp | grep -E ':(80|8123) '` et
`curl -s -o /dev/null -w "%{http_code}\n" http://localhost/` (attendu 200/302).

Si le firewall d'entreprise droppe même le port 80 entre sous-réseaux, connecter
le poste **directement** au Pi (aucun firewall entre les deux) :

**Option A — câble Ethernet direct (la plus fiable).** Débrancher le câble
corporate du Pi, le relier au Mac (adaptateur USB-C Ethernet), IP statiques des
deux côtés :

```sh
# Pi (console) :
ha network update enu1u1u1 --ipv4-method static --ipv4-address 192.168.99.1/24 --ipv4-nameserver 192.168.99.1
# Mac : adaptateur Ethernet → IPv4 manuelle 192.168.99.2/24, routeur vide
ping 192.168.99.1 && nc -zv 192.168.99.1 8123        # depuis le Mac
# navigateur : http://192.168.99.1:8123
# retour au LAN corporate ensuite : ha network update enu1u1u1 --ipv4-method auto
```

> **Piège « Problème de réseau détecté / pas d'interface primaire »** (constaté
> le 2026-11-13) : en IP statique **sans gateway**, HA OS ne désigne aucune
> interface primaire → DNS « ? » → le téléchargement de HA Core à l'installation
> initiale échoue. Correctifs :
> - activer le **partage Internet du Mac** vers l'adaptateur Ethernet (macOS :
>   Réglages Système → Général → Partage → Partage Internet : source Wi-Fi/VPN,
>   cible = adaptateur USB-C Ethernet ; le Mac fait alors NAT + DHCP + DNS en
>   **192.168.2.1**) et remettre le Pi en DHCP :
>   `ha network update enu1u1u1 --ipv4-method auto` → IP en 192.168.2.x, puis UI sur
>   `http://192.168.2.x/` ;
> - ou garder le statique mais ajouter gateway + DNS :
>   `ha network update enu1u1u1 --ipv4-method static --ipv4-address 192.168.2.10/24 --ipv4-gateway 192.168.2.1 --ipv4-nameserver 192.168.2.1`.
> Si `--ipv4-method auto` ne donne **aucune IP** : aucun serveur DHCP ne répond sur
> le lien direct → le partage Internet du Mac n'est pas actif (ou mauvaise cible
> dans Réglages → Partage ; lister les ports : `networksetup -listallhardwareports`).
> Côté Pi, vérifier que le lien est UP (`ip link show enu1u1u1`) puis forcer un
> nouveau bail : `nmcli device connect enu1u1u1` — ou passer en statique
> 192.168.2.10/24, gateway/DNS 192.168.2.1.
> Si le DNS reste `192.168.2.1` mais ne résout rien (le partage macOS ne forward
> pas fiablement le DNS) : poser un DNS **explicite** sur le Pi —
> `ha network update enu1u1u1 --ipv4-nameserver 1.1.1.1 --ipv4-nameserver 8.8.8.8` (public, si le
> réseau corporate l'autorise), ou les DNS corporate lus sur le Mac
> (`scutil --dns | grep nameserver`) ; tester depuis le Pi :
> `nslookup ghcr.io 1.1.1.1` et `curl -sI --max-time 5 https://ghcr.io`.
> Si le téléchargement de HA Core reste bloqué (hôtes ghcr.io/github.com non
> autorisés par le firewall) : rebrancher le câble corporate le temps du
> téléchargement + onboarding en API depuis le Pi en local (§3.4.1), puis
> rebasculer en lien direct pour l'UI.
> Si le DNS est renseigné mais que le téléchargement échoue quand même : le blocage
> est l'**egress HTTPS** (ghcr.io / github.com), pas le DNS. Tester depuis le Pi :
> `curl -sI --max-time 8 https://ghcr.io/v2/`. Proxy corporate (lu sur le Mac :
> `networksetup -getsecurewebproxy "Wi-Fi"`, `scutil --proxy`) → le poser sur le Pi
> si supporté : `ha network update enu1u1u1 --help | grep -i proxy` puis
> `--proxy http://<proxy>:<port>`. Repli ultime : câble corporate + test
> `curl -sI https://ghcr.io` depuis le Pi + `ha core update` pour télécharger le
> core, puis onboarding en API local — le warning disparaît ensuite. Le warning
> n'empêche pas HA de tourner (UI déjà accessible) : il ne bloque que le
> téléchargement du core.
> « `HomeAssistantCore.update` blocked from execution, no host internet
> connection » (constaté le 2026-11-13) : c'est le **check de connectivité du
> Supervisor** qui échoue. Distinguer avec, depuis le Pi :
> `curl -sI --max-time 8 https://ghcr.io/v2/ | head -1` et `nslookup ghcr.io`.
> Si curl échoue aussi → egress bloqué : poser un DNS public
> (`ha network update enu1u1u1 --ipv4-nameserver 1.1.1.1 --ipv4-nameserver 8.8.8.8`) et/ou le proxy
> corporate (lu sur le Mac : `networksetup -getsecurewebproxy "Wi-Fi"` ;
> `ha network update enu1u1u1 --help | grep -i proxy` puis `--proxy http://<proxy>:<port>`),
> puis relancer `ha core update`.
> DNS OK mais `curl https://ghcr.io` KO (constaté le 2026-11-13) = egress **TCP/443
> bloqué** (DNS autorisé, HTTPS non) → proxy corporate : lu sur le Mac avec
> `networksetup -getsecurewebproxy "Wi-Fi"`, testé depuis le Pi avec
> `curl -sI --max-time 10 -x http://<proxy>:<port> https://ghcr.io/v2/ | head -1`,
> puis posé sur le Pi : `ha network update enu1u1u1 --proxy http://<proxy>:<port>`
> (si le flag existe) et `ha core update`. Sans proxy disponible : demander à l'IT
> une allowlist **TCP/443 vers ghcr.io, github.com, objects.githubusercontent.com**
> depuis l'IP du Pi (mises à jour Home Assistant).
> Si `networksetup -getwebproxy/-getsecurewebproxy` et `scutil --proxy` ne montrent
> **aucun proxy manuel** (constaté le 2026-11-13) : le Mac utilise un proxy
> **automatique** — `networksetup -getautoproxyurl "Wi-Fi"` donne l'URL du PAC ;
> `curl -s <pac-url> | grep -i proxy` en extrait le `PROXY <host>:<port>`. Tester
> aussi sur le Mac `curl -sI --max-time 8 https://ghcr.io/v2/ | head -1` pour savoir
> si le sous-réseau Wi-Fi a l'egress 443 (le Pi, lui, ne l'a pas).
> Constaté le 2026-11-13 : aucun proxy (manuel ni PAC), Mac OK en 443 depuis le
> Wi-Fi (`HTTP/2 405`) mais Pi KO depuis 10.18.71.0/24 → deux solutions :
> (a) faire sortir le Pi **via le Mac** (câble direct + partage Internet, DNS public
> sur le Pi, puis `ha core update`) ; (b) allowlist IT **TCP/443 vers ghcr.io,
> github.com, objects.githubusercontent.com** depuis 10.18.71.168 — solution pérenne
> pour toutes les mises à jour HA ultérieures.
> « `Error: Can't update config on enu1u1u1` » (constaté le 2026-11-13) : le
> Supervisor refuse la modif partielle → logs : `docker logs hassio_supervisor
> --tail 50` ; forcer le DNS en direct via nmcli sur la connexion active :
> `CON=$(nmcli -t -f NAME,DEVICE con show --active | awk -F: '$2=="enu1u1u1"{print $1}')`,
> `nmcli con mod "$CON" ipv4.ignore-auto-dns yes ipv4.dns "1.1.1.1 8.8.8.8"`,
> `nmcli device reapply enu1u1u1`.
> « Votre connexion Internet ne peut pas être partagée, car elle est protégée par
> 802.1X » (constaté le 2026-11-13) : macOS refuse de partager le Wi-Fi corporate.
> Contournements : (a) partager depuis le **VPN** (Partage Internet : source = VPN,
> cible = adaptateur USB-C Ethernet) si le VPN est connecté — le VPN n'est pas
> 802.1X ; (b) NAT manuel sur le Mac : `sudo sysctl -w net.inet.ip.forwarding=1`,
> `echo 'nat on en0 from 192.168.99.0/24 to any -> (en0)' | sudo tee -a /etc/pf.conf`,
> `sudo pfctl -f /etc/pf.conf && sudo pfctl -e`, IP manuelle 192.168.99.1/24 sur le
> service Ethernet du Mac, Pi en statique 192.168.99.2/24 gw 192.168.99.1 DNS 1.1.1.1 ;
> (c) pérenne : allowlist IT TCP/443 depuis l'IP du Pi (voir plus haut).
> **Wi-Fi client sur le Pi** (2026-11-13) : si le Wi-Fi visé a une clé **WPA-PSK**
> (SSID invité/IoT), le Pi peut s'y joindre — console bash :
> `nmcli device wifi list` puis `nmcli device wifi connect "<SSID>" password "<clé>"`
> (ou UI : Réglages → Système → Réseau → Wi-Fi). Le sous-réseau Wi-Fi ayant l'egress
> 443 (vérifié depuis le Mac), le Pi y a Internet : `ha network info` (wlan0 avec
> IP), `curl -sI https://ghcr.io/v2/`, puis `ha core update`. Le Wi-Fi **802.1X
> entreprise (EAP + certificats) n'est pas supporté** par HA OS : le Pi ne peut pas
> s'y authentifier.
> SSID « Guest » ouvert (security « -- ») avec identifiant/mot de passe = **portail
> captif** (constaté le 2026-11-13) : association ouverte, puis auth web. Procédure :
> `nmcli device wifi connect "Guest"` (sans password) ; détecter le portail :
> `curl -sI --max-time 8 http://captive.apple.com/hotspot-detect.html` → en-tête
> `Location:` = URL du portail ; lire le formulaire :
> `curl -s <portal> | grep -iE '<form|<input|action='` ; poster les credentials
> (`curl -s -X POST <action> -d '...'` selon les champs) ; vérifier
> `curl -sI --max-time 8 https://ghcr.io/v2/ | head -1` puis `ha core update`.
> Déconnecter `enu1u1u1` pendant l'update (`nmcli device disconnect enu1u1u1`) pour
> que la route par défaut passe par wlan0. La session portail est souvent liée à
> l'adresse MAC et peut expirer → à réauthentifier.
> Si les sondes captive renvoient **vide** : vérifier d'abord l'association
> (`nmcli device status`, `ip -4 addr show wlan0`, `ip route`, `cat /etc/resolv.conf`)
> — sans IP ni route, rien ne sort ; le portail est souvent servi par la gateway :
> `GW=$(ip route | awk '/default/{print $3; exit}'); curl -s http://$GW/ | grep -iE 'form|action|input'`.

**Option B — hotspot Wi-Fi émis par le Pi** (le Wi-Fi du 3B+ supporte le mode AP ;
le Pi garde son Ethernet corporate, le Mac rejoint l'AP). Via NetworkManager sur
l'hôte HA OS :

```sh
# console (bash root) :
nmcli device status                                # wlan0 présent ?
nmcli radio wifi on
nmcli device wifi hotspot ifname wlan0 ssid PHS16-Pi password 'MotDePasseFort123'
# (si dnsmasq absent sur HA OS, cette commande échoue → repli :
#  nmcli con add type wifi ifname wlan0 con-name phs16-ap mode ap ssid PHS16-Pi \
#    802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk 'MotDePasseFort123'
#  nmcli con up phs16-ap)
ip -4 addr show wlan0                              # ex: 10.42.0.1/24 (mode shared NM)
# Mac : rejoindre le Wi-Fi "PHS16-Pi" ; si pas d'IP auto, IP manuelle 10.42.0.2/24
# navigateur : http://10.42.0.1:8123
```

Piège : le Supervisor peut supprimer la connexion AP au reboot (à recréer) ;
certaines politiques d'entreprise interdisent les AP — ici l'AP est autonome,
émis par le Pi lui-même. Erreur « **IP configuration could not be reserved** »
(constatée le 2026-11-13) : le mode `shared` de NM a besoin de dnsmasq (absent sur
HA OS) et wlan0 ne doit pas être déjà connecté en client → déconnecter d'abord
(`nmcli device disconnect wlan0`) et créer l'AP en **IP manuelle** (pas de DHCP) :

```sh
nmcli con delete phs16-ap 2>/dev/null
nmcli con add type wifi ifname wlan0 con-name phs16-ap mode ap ssid PHS16-Pi \
  802-11-wireless-security.key-mgmt wpa-psk \
  802-11-wireless-security.psk 'MotDePasseFort123' \
  ipv4.method manual ipv4.addresses 192.168.99.1/24
nmcli con up phs16-ap
ip -4 addr show wlan0                    # 192.168.99.1/24
# Mac : rejoindre PHS16-Pi, IP statique 192.168.99.2/24 (pas de DHCP sans dnsmasq)
# navigateur : http://192.168.99.1/
```

Sans luminaires, on peut aussi rejouer sur le Pi le scénario E2E sans matériel
du §3.4.1 (simulateur `fake_spot.py` sur pty + symlink stable, ex: `/tmp/phs_pty`).

### 4.3 Limites du Pi 3B+ et réglages allégés

- **1 Go de RAM** : HA OS démarre et tient pour quelques SPOT, à condition
  d'alléger :
  - ne garder que l'add-on Terminal & SSH ;
  - **limiter l'historique**, le recorder étant le plus gros consommateur de
    disque et de RAM — dans `configuration.yaml` (add-on File editor ou
    Terminal & SSH) :

    ```yaml
    recorder:
      purge_keep_days: 2       # historique court en phase de test
      commit_interval: 30      # écritures moins fréquentes
    ```

  - tableau de bord léger (quelques cartes), pas de dashboard chargé.
- **Performance** : si le Pi peine, passer l'intervalle de rafraîchissement de
  l'intégration à 30–60 s dans ses options — le protocole est en polling, rien
  n'est perdu, seuls les états mettent plus longtemps à remonter.
- Le bus RS-422 passe sans problème en USB 2.0 (le débit du protocole est
  dérisoire) : aucun souci de ce côté.

### 4.4 Checklist de validation sur le Pi 3B+ (vrais luminaires)

Reprendre la checklist du §3.5, plus :

- [ ] Redémarrage du Pi → l'intégration rouvre le port sur `/dev/phs16bus`
      (règle udev) et rescanne la ligne toute seule.
- [ ] Accès à distance via le VPN de l'entreprise (même procédure que §5.6).

> **Verdict attendu** : si tout passe sur le Pi 3B+, la même procédure passera
> sur le mini-PC du §5 — aucun changement de code, et le même nom de port
> `/dev/phs16bus` grâce à la règle udev.

---

## 5. Installation sur le PC Linux dédié (déploiement)

Cette section décrit l'installation sur la **machine cible dédiée** (mini-PC ou
Pi du §2.1), celle qui restera allumée près des luminaires. Deux voies selon le
matériel choisi. **Home Assistant OS** est recommandé : c'est l'installation la
plus plug-and-play (mises à jour, add-ons, sauvegardes intégrées, supervisor).

### 5.1 Option A — Home Assistant OS (recommandé)

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

### 5.2 Option B — Debian générique + Home Assistant en conteneur

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
  --device /dev/ttyUSB1:/dev/ttyUSB1 \   # boîtier dual uniquement (port RX)
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
```

- `--device /dev/ttyUSB0` : passe l'adaptateur USB-RS422 au conteneur
  (vérifier le port avec `ls /dev/ttyUSB*` ; le rendre stable via une règle udev
  sur le numéro de série FTDI, voir §7). En boîtier dual, passer **les deux**
  ports : `--device /dev/phs16bus:/dev/phs16bus --device /dev/phs16rx:/dev/phs16rx`.
- Premier accès : `http://<ip-du-mini-pc>:8123`, onboarding idem.

### 5.3 Installer l'intégration `phs16lc`

L'intégration vit dans ce dépôt : [`custom_components/phs16lc/`](custom_components/phs16lc/).

**Méthode 1 — copie manuelle ou script (recommandée pour un usage privé)** :

```sh
# Depuis le Mac de développement, en une commande (tar over SSH, aucun outil
# requis côté cible hormis ssh+tar) :
ha-integration/tools/deploy_to_linux.sh ha@192.168.1.50            # HA OS : /config par défaut
ha-integration/tools/deploy_to_linux.sh root@mini-pc /var/lib/hass # conteneur : chemin de la config
# puis redémarrer Home Assistant sur la cible (Réglages → Système → Redémarrer)

# Équivalent manuel (add-on Terminal & SSH sur la cible) :
mkdir -p /config/custom_components
# copier custom_components/phs16lc/ du dépôt vers /config/custom_components/phs16lc/
```

**Méthode 1b — zip de release** (pièce jointe de release GitLab, ou à déposer à la
main dans `/config/custom_components/`) :

```sh
python3 ha-integration/tools/package_release.py --dest dist   # → dist/phs16lc-<version>.zip
# layout du zip = racine du dépôt ha-integration/ : hacs.json, brand/, custom_components/phs16lc/
```

**Méthode 2 — dépôt GitHub dédié + Marketplace** (mises à jour en un clic, avec
entité « update ») : pousser **uniquement le contenu de `ha-integration/`** à la
racine d'un dépôt GitHub dédié. Ce dossier a déjà exactement le layout attendu à
la racine d'un dépôt Marketplace : `hacs.json`, `brand/`, `README.md` et
`custom_components/phs16lc/` (layout vérifié par `tests/test_release.py`).

```sh
cd /Users/ptocquin/RunningProjects/phs16lc

# 1. Créer un dépôt GitHub VIDE dédié (ex: github.com/ptocquin/phs16lc-ha),
#    public recommandé (un dépôt privé fonctionne avec un PAT dans l'URL :
#    https://<token>@github.com/ptocquin/phs16lc-ha.git)
git remote add ha-dist https://github.com/ptocquin/phs16lc-ha.git

# 2. Premier push : `git subtree push` construit un historique synthétique
#    ne contenant QUE ha-integration/ et le pousse sur la branche main
git subtree push --prefix=ha-integration ha-dist main

# 3. À chaque nouvelle version : bump de "version" dans
#    ha-integration/custom_components/phs16lc/manifest.json, commit, tag vX.Y.Z,
#    puis re-push :
git subtree push --prefix=ha-integration ha-dist main
```

> HA ne lit que `hacs.json` et `custom_components/` à la racine du dépôt : les
> fichiers auxiliaires poussés avec (`tests/`, `tools/`, `pyproject.toml`,
> `dist/*.zip`) sont simplement ignorés. Ne pas initialiser le dépôt GitHub avec
> un README (sinon le premier `subtree push` refusera de pousser sur `main`).

Dans HA (2026.11 : le **Marketplace est intégré** à Réglages, plus besoin de
l'add-on HACS) : Réglages → Marketplace → ⋮ → **Dépôts personnalisés** → coller
l'URL du dépôt, catégorie « Intégrations » → la carte « PHS16-LC » apparaît →
**Installer** → redémarrer HA → Réglages → Appareils et services → Ajouter une
intégration → « PHS16-LC » (puis paramétrage §5.4).

> Le Marketplace affiche un avertissement : le contenu communautaire n'est ni
> testé ni supporté par le projet Home Assistant. C'est attendu pour une
> intégration privée.

### 5.4 Premier paramétrage de l'intégration

Réglages → Appareils et services → **Ajouter une intégration** → chercher
**« PHS16-LC »** → formulaire :

| Champ | Valeur | Détail |
| --- | --- | --- |
| Port série | `/dev/ttyUSB0` sur le PC Linux (liste déroulante des ports détectés, ou saisie manuelle) ; `/dev/cu.usbserial-XXXX` sur le Mac de développement (§3) | L'adaptateur FTDI doit être branché. C'est le port **TX** (émission) |
| Port série RX (optionnel) | vide par défaut | **Boîtier dual du fabricant (2× USB-RS485-WE)** uniquement : indiquez ici le second port série (réception, paire RX pins 7-8). Vide = un seul convertisseur full duplex (TX = RX). L'alimentation 12–24 V du bus est injectée par le boîtier |
| Nombre de SPOT attendus | ex: `4` | Le scan s'arrête au premier silence ; ce réglage permet de détecter une carte HS au milieu de la ligne (équivalent `--expected` de la CLI) |
| Intervalle de rafraîchissement | `10` s (5–60) | Le protocole ne pousse pas d'état : HA interroge les cartes (`@GP`, `@GT`) à cet intervalle |
| Dossier des recettes | `/config/phs16lc/recipes` | Dossier par défaut. **Depuis la v1.3.0, recettes/scènes/groups sont embarquées dans l'intégration et copiées automatiquement** vers `<config>/phs16lc/{recipes,scenes,groups.json}` au premier démarrage (si absentes — jamais d'écrasement). Pour ajouter les vôtres : copiez vos `*.json` dans ce dossier (voir ci-dessous) |

```sh
# Les recettes/scènes d'exemple (croissance, floraison, spectre, serre) et un
# groups.json d'exemple sont embarqués dans l'intégration et copiés
# AUTOMATIQUEMENT au premier démarrage vers <config>/phs16lc/ :
#   custom_components/phs16lc/recipes/*.json  -> <config>/phs16lc/recipes/
#   custom_components/phs16lc/scenes/*.json   -> <config>/phs16lc/scenes/
#   custom_components/phs16lc/groups.json     -> <config>/phs16lc/groups.json
# (copie « si absent » : vos fichiers existants ne sont jamais écrasés).
#
# HA OS 16+ : dans l'add-on Terminal & SSH la config est montée en /homeassistant
# (plus /config) ; le conteneur core la voit en /config — c'est le MÊME dossier
# physique. L'intégration résout automatiquement /config ↔ /homeassistant.
# Pour AJOUTER vos propres recettes/scènes/groupes : éditez directement
#   /homeassistant/phs16lc/recipes/*.json      (depuis l'add-on SSH, HA OS 16+)
#   /homeassistant/phs16lc/scenes/*.json
#   /homeassistant/phs16lc/groups.json
# ou /config/phs16lc/... sur un conteneur classique.
```

> **Listes vides / boutons « Scène » absents** : depuis la v1.3.0 les fichiers
> par défaut sont copiés auto ; si le dossier a été supprimé ou si `recipes_dir`
> est personnalisé et vide, les listes « Recette »/« Groupe » sont vides et aucun
> bouton « Scène » n'apparaît — l'intégration logue un warning au démarrage, et
> les diagnostics (Réglages → Système → Réparations → Télécharger les diagnostics)
> indiquent `recipes_dir` et `groups_file` (configuré vs résolu, existence,
> nombre de fichiers, groupes chargés). Les listes et groupes se remplissent
> **sans redémarrer** : relus à chaque cycle de polling (10 s par défaut) ou juste
> après « Scanner la ligne ».

### 5.5 Vérification de l'installation

1. **Scan** : appuyer sur le bouton « Scanner la ligne » (ou service
   `phs16lc.scan`) → les cartes détectées apparaissent comme *devices*
   (« SPOT 1 », « SPOT 2 »…) reliés au hub « Adaptateur PHS16-LC ».
2. **Entités** : chaque SPOT a une lampe (`light`), deux listes déroulantes
   (recette / groupe), un bouton « Sauvegarder NVM », 3 capteurs de température,
   un résumé des courants et un capteur de présence. Chaque **groupe** de
   `groups.json` a son device avec lampe + liste « Recette » + bouton
   « Sauvegarder NVM » (§6.8), et chaque SPOT membre porte le **badge coloré**
   (label) du groupe.
3. **Test rapide** : allumer/éteindre la lampe « SPOT 1 » depuis le tableau de
   bord, vérifier que les vraies LED réagissent.
4. Sans matériel, on peut valider tout le flux avec le simulateur :
   `../light-monitor/tools/fake_spot.py --boards 3` (voir PLAN §3.1).

### 5.6 Accès à distance

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

## 6. Utilisation

### 6.1 Les entités par luminaire

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

### 6.2 Allumer / éteindre / régler l'intensité

- Carte par carte via la lampe, ou **toutes les cartes** via une automation
  ciblant `light.phs16lc_spot_*` (ou le service `phs16lc.apply_recipe` avec
  `address: all`).
- Correspondance curseur → courant : `mA = 74 + (2150 − 74) × % / 100`
  (ex: 50 % ≈ 1112 mA). En dessous de 74 mA, le canal est éteint.

### 6.3 Recettes lumineuses et scènes

Les recettes sont les fichiers JSON copiés dans `/config/phs16lc/recipes/`
(format documenté dans [`../GUIDE.md`](../GUIDE.md) §5 : vecteur `channels`
ou `groups`). Pour en ajouter : copier le fichier dans ce dossier, puis
« Scanner » ou redémarrer l'intégration pour rafraîchir les listes.

Les scènes (`/config/phs16lc/scenes/*.json`) apparaissent comme des boutons
« Scène <nom> ».

### 6.4 Supervision et historique

- **Historique** (barre latérale « Historique ») : courbes de température et
  états des lampes, sur la durée de rétention configurée
  (Réglages → Système → Statistiques → ou `recorder:` dans `configuration.yaml`).
- **Logbook** : chaque recette/scène/sauvegarde apparaît comme événement
  (`phs16lc_recipe_applied`, `phs16lc_scene_applied`, `phs16lc_saved`).
- **Statistiques** : pour grapher les températures sur le long terme.

### 6.5 Exemples d'automations (YAML)

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

### 6.6 Services avancés

Disponibles dans Outils de développement → Services :
`phs16lc.scan`, `phs16lc.apply_recipe`, `phs16lc.apply_scene`, `phs16lc.save`,
`phs16lc.set_channels` (16 valeurs mA), `phs16lc.set_channel` (un canal).

### 6.7 Coexistence avec la CLI `phs16ctl`

La CLI (`../phs16ctl/`) et l'intégration HA **ne doivent pas tourner en même
temps sur le même port série** (`/dev/ttyUSB0` ne s'ouvre qu'une fois ; en
boîtier dual : les deux ports TX et RX). Pour intervenir en CLI :
`phs16ctl --port /dev/phs16bus --rx-port /dev/phs16rx …`, après avoir retiré
temporairement l'intégration (Réglages → Appareils et services → PHS16-LC →
Supprimer), ou utiliser un autre port/adaptateur.

### 6.8 Groupes de luminaires (recette de groupe, badges tag + couleur)

Depuis la **v1.3.0**, un **groupe de luminaires** (ex. une rangée d'une serre)
est défini dans `<config>/phs16lc/groups.json` (copié auto au premier démarrage
depuis l'exemple embarqué ; éditez-le ensuite directement dans la config HA) :

```json
{
  "serre_1_nord": {
    "name": "Serre 1 — Nord",
    "color": "#4CAF50",
    "icon": "mdi:leaf",
    "area": "serre_1",
    "addresses": [1, 2, 3, 4]
  }
}
```

- `addresses` : adresses des SPOT membres. `color` + `icon` : **badge coloré**
  posé comme *label HA* sur le device de chaque membre (HA 2026.11 supporte la
  couleur des labels) → visible sur la carte de chaque luminaire du groupe.
- `area` (optionnel) : crée l'area si absente et la pose sur les devices membres
  → la pièce apparaît dans l'UI avec tous ses luminaires.
- Le fichier est **relu à chaque cycle de polling** : modifier `groups.json` prend
  effet en ≤ 10 s, sans redémarrer (les entités du nouveau groupe apparaissent
> seules ; la synchro des labels/areas est additive — elle ne retire jamais un
> label posé à la main).

**Entités créées par groupe** (device « Groupe <name> », relié au hub) :

| Entité | Utilisation |
| --- | --- |
| `light.phs16lc_group_<id>` | On/off + luminosité appliqués à **tous les membres**. « On » sans curseur = dernière recette de chaque membre (D11), ou 500 mA si aucune. |
| `select.phs16lc_group_<id>_recette` | Applique la recette choisie à **tous les membres** en une fois. |
| `button.phs16lc_group_<id>_save` | « Sauvegarder NVM » (@WP) sur tous les membres. |

**Services** : `address` accepte désormais `"group:<id>"` en plus de l'entier et
`"all"` — ex. photopériode d'un groupe en une ligne :

```yaml
- service: phs16lc.apply_recipe
  data:
    address: "group:serre_1_nord"
    recipe: croissance.json
```

Un membre en erreur n'interrompt pas les autres (événements
`phs16lc_recipe_applied` par carte + récapitulatif `phs16lc_group_recipe_applied`
dans le logbook). Blueprint embarqué « PHS16-LC — Recette planifiée d'un groupe
de luminaires » pour la photopériode d'un groupe via son schedule.

> Le générateur de dashboards (`dashboards/generate_dashboards.py`) lit le même
> `groups.json` (`--groups`, ou `dashboards/groups.json` par défaut) : une seule
> source de vérité pour les groupes, partagée entre l'intégration (runtime) et
> les dashboards générés.

---

## 7. Dépannage

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| Aucune entité après l'ajout de l'intégration | Dossier mal copié / pas de redémarrage | Vérifier `/config/custom_components/phs16lc/manifest.json`, redémarrer HA, voir les logs (Réglages → Système → Journaux) |
| « Impossible d'ouvrir le port » | Mauvais port, ou port déjà utilisé (CLI lancée en parallèle) | Choisir le bon port dans les options de l'intégration ; arrêter la CLI |
| `scan` trouve 0 carte | Alim 12–24 V absente du bus, mauvais port, ordre TX/RX inversé (dual) | Mesurer 12–24 V entre pins 3/6 (+) et 4/5 (masse) à la prise RJ45 du luminaire ; en boîtier dual, TX = port câblé sur pins 1-2, RX = pins 7-8 ; voir [`../GUIDE.md`](../GUIDE.md) §6 (inverser paires 1-2 ↔ 7-8) |
| Carte « hors ligne » au milieu de la ligne | Trou dans le bus : le scan s'arrête au 1er silence | Renseigner « nombre de SPOT attendus » dans les options de l'intégration |
| Changements perdus après coupure de courant | `@SP` volatile, pas de `@WP` | Bouton « Sauvegarder NVM », ou option `save: true` des services |
| NAK 5 (checksum) | Parasites, bus long non terminé | Terminaison 100 Ω en bout de ligne (GUIDE racine §1.2) |
| Conteneur Docker : port absent | `--device` manquant | Relancer avec `--device /dev/ttyUSB0:/dev/ttyUSB0` (en boîtier dual : les **deux** ports, `--device` ×2) ; rendre le port stable par règle udev (ID_SERIAL FTDI) |
| `curl http://<ip>:8123` → `000` depuis un poste du LAN | Mauvaise IP, sous-réseau/VLAN différent, VPN actif, isolement client Wi-Fi, ou ACL réseau (DROP) | Côté Pi (console) : `ha network info`, `ss -tlnp \| grep 8123` (attendu `0.0.0.0:8123`), `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8123` (attendu 200/302). Côté poste : `netstat -rn \| grep <ip>`, `ping <ip>`, `nc -zv <ip> 8123`. Timeout = DROP → demander l'ACL TCP/8123 à l'IT ; ping KO → vérifier IP/VLAN/VPN ; Wi-Fi d'entreprise = souvent isolement client → poste filaire ou VPN |
| Lenteurs d'affichage | Polling trop fréquent | Augmenter l'intervalle de rafraîchissement dans les options (max 60 s) |
| Pas de `/dev/cu.usbserial-*` sur le Mac (macOS ≥ 26.6) | Pilote FTDI VCP non installé ou extension non validée | Installer le pilote VCP (ftdichip.com) + valider dans *Réglages Système → Confidentialité et sécurité*, redémarrer (`../README.md` §7.2) |
| Mauvais nom de port sur Mac | `tty.` au lieu de `cu.` | Utiliser `/dev/cu.usbserial-XXXX` (préfixe `cu.`) |
| `hass` refuse de démarrer sur le Mac | Python < 3.14.2 ou lancement hors venv (HA 2026.11) | Lancer via le venv uv 3.14 : `.venv-ha/bin/hass -c ~/.hass_dev` (§3.4) |
| Port série absent dans un conteneur sur Mac | Pas de passthrough USB fiable sur Docker Desktop / `container` macOS | Sur Mac, développer en venv `hass -c` (§3.4) ; réserver Docker au PC Linux cible ou aux tests pty |

Rendre le port série stable (udev) :

```sh
# /etc/udev/rules.d/99-phs16.rules
# montage A (un seul adaptateur) :
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="phs16bus"
# → le port apparaîtra toujours comme /dev/phs16bus
# montage B (boîtier dual, deux câbles) : un symlink par n° de série du câble
# (n° lu via : ls -l /dev/serial/by-id/) :
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ENV{ID_SERIAL_SHORT}=="FTXXXXXXX", SYMLINK+="phs16tx"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ENV{ID_SERIAL_SHORT}=="FTYYYYYYY", SYMLINK+="phs16rx"
# → /dev/phs16tx (câble sur pins 1-2) et /dev/phs16rx (câble sur pins 7-8)
```

---

## 8. Mise à jour de l'intégration

- **Copie manuelle** : recopier `custom_components/phs16lc/` (version plus
  récente) puis redémarrer HA.
- **Dépôt privé (Marketplace)** : l'entité « update » de `phs16lc` apparaît dans
  Réglages → Mises à jour ; un « repair » proposera le redémarrage.

## 9. Limites connues (à date de la v0.2)

- Le protocole PHS16-LC ne pousse pas d'état : l'affichage reflète un polling
  (10 s par défaut) — une commande manuelle externe (CLI) n'est visible qu'au
  prochain rafraîchissement.
- Une entité `light` = intensité **uniforme** sur les 16 canaux ; les réglages
  par groupe passent par les listes « Recette/Groupe » ou les services.
- Un seul bus par instance de l'intégration ; plusieurs bus = plusieurs
  entrées de configuration. En boîtier dual, une entrée ouvre **deux** ports
  série (TX + RX) — ne pas inverser leurs rôles dans le formulaire.
- L'instance HA tournant en venv sur le MacBook Pro (§3.4) est un environnement
  de **développement** : la production tourne sur le PC Linux dédié (§5).
