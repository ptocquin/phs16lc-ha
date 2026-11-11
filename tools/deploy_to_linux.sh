#!/bin/sh
# Déploie l'intégration phs16lc sur la machine Linux dédiée (HA OS ou conteneur)
# par SSH, sans outil autre que tar/ssh côté cible.
#
# Usage :
#   tools/deploy_to_linux.sh <cible-ssh> [config-dir]
#   ex. : tools/deploy_to_linux.sh ha@192.168.1.50            # config-dir = /config (HA OS)
#         tools/deploy_to_linux.sh root@mini-pc.local /var/lib/hass
#
# Le chemin par défaut /config convient à Home Assistant OS (dossier /config
# partagé). Aucun changement de code : seul le port série diffère sur la cible
# (/dev/ttyUSB0 ou /dev/phs16bus, voir GUIDE §6).
set -eu

HOST=${1:?usage: deploy_to_linux.sh <cible-ssh> [config-dir]}
CONFIG_DIR=${2:-/config}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

tar czf - -C "$ROOT/custom_components" --exclude='__pycache__' --exclude='*.pyc' phs16lc \
  | ssh "$HOST" "mkdir -p '$CONFIG_DIR/custom_components' \
    && tar xzf - -C '$CONFIG_DIR/custom_components' \
    && find '$CONFIG_DIR/custom_components/phs16lc' -type d -name __pycache__ -prune -exec rm -rf {} +"

echo "Intégration copiée sur $HOST:$CONFIG_DIR/custom_components/phs16lc"
echo "Redémarrer Home Assistant sur la cible (Réglages → Système → Redémarrer)."
