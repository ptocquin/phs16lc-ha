"""Génère la configuration Home Assistant « Culture » à partir de mapping.yaml.

Usage (depuis ha-integration/) :

    uv run python dashboards/generate_dashboards.py            # mapping par défaut
    uv run python dashboards/generate_dashboards.py --mapping dashboards/mapping.yaml \
        --out dashboards/generated

Produit dans dashboards/generated/ :

    groups.yaml              light groups (sous-groupes + par chambre)   -> `light: !include ...`
    templates_alertes.yaml   capteurs agrégés par chambre (temp max, HS) -> `template: !include ...`
    automations_alertes.yaml alertes température / carte HS           -> `automation: !include ...`
    scripts.yaml             script « tout sauvegarder en NVM »          -> `script: !include ...`
    dashboard_culture.yaml   dashboard Lovelace complet (vues sections)
    helpers_a_creer.md       liste des helpers/blueprints à créer dans l'UI

Conventions de nommage : voir l'en-tête de mapping.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

TEMP_KEYS = ("cpu", "led1", "led2")
SEUIL_TEMP_ALERTE = 65  # °C, repris dans les gauges et les alertes


# ---------------------------------------------------------------------------
# Conventions de nommage
# ---------------------------------------------------------------------------


def label(ch: str, g: str) -> str:
    return f"{ch}_{g}"


def light_groupe(ch: str, g: str) -> str:
    return f"light.{ch}_groupe_{g}"


def light_tous(ch: str) -> str:
    return f"light.{ch}_tous"


def schedule(ch: str, g: str) -> str:
    return f"schedule.photo_{ch}_{g}"


def manuel(ch: str, g: str) -> str:
    return f"input_boolean.manuel_{ch}_{g}"


def recette(ch: str, g: str) -> str:
    return f"input_select.recette_{ch}_{g}"


# ---------------------------------------------------------------------------
# Chargement et validation du mapping
# ---------------------------------------------------------------------------


def load_chambres(mapping_path: Path) -> dict[str, dict]:
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    chambres = data.get("chambres") or {}
    if not chambres:
        sys.exit(f"mapping vide ou sans clé 'chambres' : {mapping_path}")
    for ch, cfg in chambres.items():
        spots = [int(s) for g in (cfg.get("groupes") or {}).values() for s in g]
        if not spots:
            print(f"WARNING: chambre '{ch}' sans SPOT — ignorée (remplis mapping.yaml)")
            continue
        vus = set()
        for g, liste in (cfg.get("groupes") or {}).items():
            for s in liste:
                if int(s) in vus:
                    print(f"WARNING: SPOT {s} dans plusieurs groupes de '{ch}'")
                vus.add(int(s))
        cfg["_spots"] = sorted(vus)
        cfg["_coords"] = {str(k): v for k, v in (cfg.get("coords") or {}).items()}
        for s in cfg["_spots"]:
            if str(s) not in cfg["_coords"]:
                print(f"WARNING: SPOT {s} de '{ch}' sans coordonnées plan — positionné à 50%/50%")
                cfg["_coords"][str(s)] = {"top": 50, "left": 50}
    return {ch: cfg for ch, cfg in chambres.items() if cfg.get("_spots")}


# ---------------------------------------------------------------------------
# Générateurs
# ---------------------------------------------------------------------------


def gen_groups(chambres: dict[str, dict]) -> list[dict]:
    """Light groups : un par sous-groupe, un « tous » par chambre."""
    out = []
    for ch, cfg in chambres.items():
        for g in cfg.get("groupes") or {}:
            out.append(
                {
                    "platform": "group",
                    "name": f"{cfg['nom']} — Groupe {g}",
                    "unique_id": f"{ch}_groupe_{g}",
                    "entities": [f"light.spot_{s}" for s in sorted(cfg["groupes"][g], key=int)],
                }
            )
        out.append(
            {
                "platform": "group",
                "name": f"{cfg['nom']} — Tous",
                "unique_id": f"{ch}_tous",
                "entities": [light_groupe(ch, g) for g in cfg.get("groupes") or {}],
            }
        )
    return out


def _picture_elements(ch: str, cfg: dict) -> dict:
    pe: dict = {"type": "picture-elements", "image": cfg["plan"], "elements": []}
    for g, img in (cfg.get("zones") or {}).items():
        pe["elements"].append(
            {
                "type": "image",
                "image": img,
                "style": {"top": "0%", "left": "0%", "width": "100%"},
                "tap_action": {"action": "none"},
            }
        )
    for s in cfg["_spots"]:
        c = cfg["_coords"][str(s)]
        top, left = int(c["top"]), int(c["left"])
        pe["elements"].append(
            {
                "type": "state-icon",
                "entity": f"light.spot_{s}",
                "icon": "mdi:lightbulb",
                "tap_action": {"action": "toggle"},
                "hold_action": {"action": "more-info"},
                "style": {"top": f"{top}%", "left": f"{left}%"},
                "state": [{"value": "off", "style": {"filter": "grayscale(1)", "opacity": 0.35}}],
            }
        )
        pe["elements"].append(
            {
                "type": "state-badge",
                "entity": f"sensor.spot_{s}_temp_cpu",
                "style": {"top": f"{max(0, top - 7)}%", "left": f"{max(0, left - 1)}%"},
                "state": [
                    {
                        "operator": ">",
                        "value": 60,
                        "style": {"color": "#ff5252", "--state-badge-color": "#ff5252"},
                    }
                ],
            }
        )
        pe["elements"].append(
            {
                "type": "state-badge",
                "entity": f"binary_sensor.spot_{s}_online",
                "icon": "mdi:lan",
                "style": {"top": f"{min(95, top + 7)}%", "left": f"{max(0, left - 1)}%"},
                "state": [
                    {
                        "value": "off",
                        "style": {"color": "#ff5252", "--state-badge-color": "#ff5252"},
                    }
                ],
            }
        )
    return pe


def gen_dashboard(chambres: dict[str, dict]) -> dict:
    views = []

    # --- Vue d'ensemble -----------------------------------------------------
    cards = [
        {
            "type": "markdown",
            "content": (
                "**À l'install** : poser les labels `<chambre>_<groupe>` sur les devices SPOT, "
                "créer areas + helpers (voir `dashboards/generated/helpers_a_creer.md`), "
                "ajuster l'entity_id du capteur `line_status` (device hub, dépend du port série)."
            ),
        }
    ]
    for ch, cfg in chambres.items():
        cards.append(
            {
                "type": "tile",
                "entity": light_tous(ch),
                "name": cfg["nom"],
                "icon": "mdi:sprout",
                "tap_action": {"action": "navigate", "navigation_path": f"/culture/{ch}"},
                "features": [{"type": "light-brightness"}],
            }
        )
        cards.append(
            {"type": "tile", "entity": f"sensor.{ch}_temp_max", "name": f"{cfg['nom']} — temp max"}
        )
        cards.append(
            {
                "type": "tile",
                "entity": f"binary_sensor.{ch}_hors_ligne",
                "name": f"{cfg['nom']} — carte HS",
            }
        )
    cards.append(
        {"type": "tile", "entity": "sensor.phs16_lc_line_status", "name": "Cartes en ligne (bus)"}
    )
    views.append(
        {
            "title": "Vue d'ensemble",
            "path": "overview",
            "type": "sections",
            "sections": [{"type": "grid", "cards": cards}],
        }
    )

    # --- Une vue par chambre : plan + liste ---------------------------------
    for ch, cfg in chambres.items():
        plan_card = _picture_elements(ch, cfg)
        liste_cards = [
            {
                "type": "markdown",
                "content": "**Attention** — ne pas régler la **luminosité** d'un groupe : "
                "cela envoie un courant uniforme aux 16 canaux de chaque SPOT et écrase "
                "la recette. On/off OK (la recette se réapplique), intensité = recette.",
            }
        ]
        for g in cfg.get("groupes") or {}:
            liste_cards.append(
                {
                    "type": "custom:auto-entities",
                    "card": {"type": "entities", "title": f"Groupe {g}"},
                    "filter": {"include": [{"domain": "light", "label": label(ch, g)}]},
                    "sort": {"method": "name"},
                }
            )
            liste_cards.append(
                {
                    "type": "tile",
                    "entity": light_groupe(ch, g),
                    "name": f"Groupe {g}",
                    "features": [{"type": "light-brightness"}],
                }
            )
            liste_cards.append(
                {
                    "type": "tile",
                    "entity": manuel(ch, g),
                    "name": f"Manuel — {g}",
                }
            )
        views.append(
            {
                "title": cfg["nom"],
                "path": ch,
                "type": "sections",
                "sections": [
                    {"type": "grid", "cards": [plan_card]},
                    {"type": "grid", "cards": liste_cards},
                ],
            }
        )

    # --- Programmes ----------------------------------------------------------
    cards = [
        {
            "type": "entities",
            "title": "Photopériodes (cliquer pour éditer les horaires)",
            "entities": [
                schedule(ch, g) for ch, cfg in chambres.items() for g in cfg.get("groupes") or {}
            ],
        },
        {
            "type": "entities",
            "title": "Modes manuels (ON = l'automatisation ne touche à rien)",
            "entities": [
                manuel(ch, g) for ch, cfg in chambres.items() for g in cfg.get("groupes") or {}
            ],
        },
        {
            "type": "entities",
            "title": "Recettes par groupe",
            "entities": [
                recette(ch, g) for ch, cfg in chambres.items() for g in cfg.get("groupes") or {}
            ],
        },
        {
            "type": "tile",
            "entity": "script.phs16lc_save_nvm_all",
            "name": "Tout sauvegarder en NVM (@WP)",
        },
        {
            "type": "markdown",
            "content": "Boutons **Scanner la ligne** et **Scène …** : sur le device hub PHS16-LC "
            "(entity_id dépendant du port série, ex. `button.phs16_lc_dev_ttyusb0_scan`).",
        },
    ]
    views.append(
        {
            "title": "Programmes",
            "path": "programmes",
            "type": "sections",
            "sections": [{"type": "grid", "cards": cards}],
        }
    )

    # --- Monitoring ----------------------------------------------------------
    cards = []
    for ch, cfg in chambres.items():
        cards.append(
            {
                "type": "custom:mini-graph-card",
                "name": f"{cfg['nom']} — températures",
                "entities": [f"sensor.spot_{s}_temp_{k}" for s in cfg["_spots"] for k in TEMP_KEYS],
                "line_width": 2,
                "show": {"legend": True, "points": False},
            }
        )
        cards.append(
            {
                "type": "gauge",
                "name": f"{cfg['nom']} — temp max",
                "entity": f"sensor.{ch}_temp_max",
                "min": 0,
                "max": 80,
                "severity": {"green": 0, "yellow": 50, "red": SEUIL_TEMP_ALERTE},
            }
        )
    views.append(
        {
            "title": "Monitoring",
            "path": "monitoring",
            "type": "sections",
            "sections": [{"type": "grid", "cards": cards}],
        }
    )

    return {"title": "Culture", "icon": "mdi:sprout", "views": views}


def gen_templates(chambres: dict[str, dict]) -> list[dict]:
    """Capteurs agrégés par chambre : température max + présence d'une carte HS."""
    out = []
    for ch, cfg in chambres.items():
        out.append(
            {
                "sensor": [
                    {
                        "name": f"{cfg['nom']} — Température max",
                        "unique_id": f"{ch}_temp_max",
                        "unit_of_measurement": "°C",
                        "state_class": "measurement",
                        "state": (
                            "{% set t = area_entities('" + ch + "')"
                            r" | select('match', 'sensor\.spot_\d+_temp_')"
                            " | map('states') | map('float', 0) | list %}"
                            "{{ t | max if t else 'unknown' }}"
                        ),
                    }
                ]
            }
        )
        out.append(
            {
                "binary_sensor": [
                    {
                        "name": f"{cfg['nom']} — Carte hors ligne",
                        "unique_id": f"{ch}_hors_ligne",
                        "state": (
                            "{% set off = area_entities('" + ch + "')"
                            r" | select('match', 'binary_sensor\.spot_\d+_online')"
                            " | select('is_state', 'off') | list %}"
                            "{{ 'on' if off | count > 0 else 'off' }}"
                        ),
                    }
                ]
            }
        )
    return out


def gen_alert_automations(chambres: dict[str, dict]) -> list[dict]:
    out = []
    for ch, cfg in chambres.items():
        out.append(
            {
                "alias": f"PHS16-LC — Alerte {cfg['nom']}",
                "trigger": [
                    {
                        "platform": "numeric_state",
                        "entity_id": f"sensor.{ch}_temp_max",
                        "above": SEUIL_TEMP_ALERTE,
                    },
                    {
                        "platform": "state",
                        "entity_id": f"binary_sensor.{ch}_hors_ligne",
                        "to": "on",
                    },
                ],
                "action": [
                    {
                        "service": "persistent_notification.create",
                        "data": {
                            "title": f"PHS16-LC — {cfg['nom']}",
                            "message": "{{ trigger.entity_id }} → {{ trigger.to_state.state }}",
                        },
                    },
                    # TODO: notification mobile, ex. :
                    # {"service": "notify.mobile_app_mon_telephone",
                    #  "data": {"title": "PHS16-LC — Serre", "message": "{{ trigger.entity_id }}"}},
                ],
                "mode": "queued",
            }
        )
    return out


SCRIPTS = {
    "phs16lc_save_nvm_all": {
        "alias": "PHS16-LC — Tout sauvegarder en NVM (@WP all)",
        "sequence": [{"service": "phs16lc.save", "data": {"address": "all"}}],
    },
}


def gen_helpers_md(chambres: dict[str, dict]) -> str:
    lignes = [
        "# Helpers et blueprints à créer dans l'UI (généré — ne pas éditer)",
        "",
        "Conventions : `schedule.photo_<ch>_<groupe>`, `input_boolean.manuel_<ch>_<groupe>`,",
        "`input_select.recette_<ch>_<groupe>`, label `<ch>_<groupe>` sur chaque device SPOT.",
        "",
    ]
    for ch, cfg in chambres.items():
        lignes.append(f"## {cfg['nom']} (area `{ch}`)")
        lignes.append("")
        for g, spots in (cfg.get("groupes") or {}).items():
            spots_txt = ", ".join(f"SPOT {s}" for s in sorted(spots, key=int))
            lignes += [
                f"### Groupe `{g}` — {spots_txt}",
                "",
                f"- label `{label(ch, g)}` à poser sur chaque device SPOT du groupe",
                f"- helper **Programme** (schedule) : `schedule.photo_{ch}_{g}`",
                f"- helper **Booléen** : `input_boolean.manuel_{ch}_{g}`",
                f"- helper **Liste déroulante** : `input_select.recette_{ch}_{g}` "
                "(options = noms des fichiers `/config/phs16lc/recipes/*.json`)",
                f"- blueprint **Photopériode d'un groupe** : programme=`schedule.photo_{ch}_{g}`, "
                f"cible=`light.{ch}_groupe_{g}`, mode manuel=`input_boolean.manuel_{ch}_{g}`",
                f"- blueprint **Recette d'un groupe** : select=`input_select.recette_{ch}_{g}`, "
                f"groupe=`light.{ch}_groupe_{g}`",
                "",
            ]
    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


def dump(path: Path, data, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {header}\n")
        f.write("# Généré par dashboards/generate_dashboards.py — ne pas éditer à la main.\n")
        yaml.safe_dump(
            data, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mapping", type=Path, default=HERE / "mapping.yaml")
    ap.add_argument("--out", type=Path, default=HERE / "generated")
    args = ap.parse_args()

    chambres = load_chambres(args.mapping)
    out = args.out

    dump(
        out / "groups.yaml",
        gen_groups(chambres),
        "Light groups (sous-groupes + par chambre). "
        "Inclure via `light: !include dashboards/generated/groups.yaml`",
    )
    dump(
        out / "dashboard_culture.yaml",
        gen_dashboard(chambres),
        "Dashboard Lovelace « Culture » (vues sections).",
    )
    dump(
        out / "templates_alertes.yaml",
        gen_templates(chambres),
        "Template sensors par chambre. "
        "Inclure via `template: !include dashboards/generated/templates_alertes.yaml`",
    )
    dump(
        out / "automations_alertes.yaml",
        gen_alert_automations(chambres),
        "Alertes température / carte HS. "
        "Inclure via `automation: !include dashboards/generated/automations_alertes.yaml`",
    )
    dump(
        out / "scripts.yaml",
        SCRIPTS,
        "Scripts. Inclure via `script: !include dashboards/generated/scripts.yaml`",
    )
    (out / "helpers_a_creer.md").write_text(gen_helpers_md(chambres), encoding="utf-8")

    n_spots = sum(len(c["_spots"]) for c in chambres.values())
    n_groupes = sum(len(c.get("groupes") or {}) for c in chambres.values())
    print(f"OK: {len(chambres)} chambre(s), {n_groupes} groupe(s), {n_spots} SPOT")
    print(f"Fichiers écrits dans {out}/ :")
    for p in sorted(out.iterdir()):
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
