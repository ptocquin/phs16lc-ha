"""Configuration utilisateur de phs16ctl : profils nommés et historique.

Tout est stocké dans `~/.config/phs16ctl/` (ou `$XDG_CONFIG_HOME/phs16ctl/`) :

- `profiles.json` : profils nommés → chemin de recette
  (le profil « default » est la recette appliquée au boot) ;
- `history.csv`   : historique des recettes appliquées (une ligne par action).
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROFILES_FILE = "profiles.json"
HISTORY_FILE = "history.csv"
HISTORY_HEADER = ["timestamp", "commande", "adresse", "recette", "groupe", "resultat"]

#: Nom du profil appliqué « au boot » (à brancher sur un script/timer système).
DEFAULT_PROFILE = "default"


def config_dir() -> Path:
    """Dossier de configuration utilisateur (`$XDG_CONFIG_HOME/phs16ctl` ou `~/.config/phs16ctl`)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "phs16ctl"


class ProfileStore:
    """Stockage des profils nommés dans `profiles.json`."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or config_dir()
        self.path = self.directory / PROFILES_FILE

    def _load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, profiles: dict[str, str]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def list(self) -> dict[str, str]:
        """Retourne {nom: chemin de recette}, trié par nom."""
        return dict(sorted(self._load().items()))

    def add(self, name: str, recipe_path: str | Path) -> None:
        """Enregistre un profil (chemin de recette résolu en absolu)."""
        profiles = self._load()
        profiles[name] = str(Path(recipe_path).resolve())
        self._save(profiles)

    def remove(self, name: str) -> None:
        """Supprime un profil ; lève KeyError s'il n'existe pas."""
        profiles = self._load()
        del profiles[name]
        self._save(profiles)

    def get(self, name: str) -> Path:
        """Chemin de recette d'un profil ; lève KeyError s'il n'existe pas."""
        return Path(self._load()[name])


@dataclass
class HistoryEntry:
    """Une ligne d'historique (recette appliquée)."""

    timestamp: str
    commande: str      # recipe | scene | profile
    adresse: str       # numéro de carte, ou « toutes » (--all), ou « scène »
    recette: str
    groupe: str        # nom du groupe, ou chaîne vide
    resultat: str      # OK ou message d'erreur

    def as_row(self) -> list[str]:
        return [self.timestamp, self.commande, self.adresse, self.recette, self.groupe, self.resultat]


def append_history(entry: HistoryEntry, directory: Path | None = None) -> None:
    """Ajoute une ligne à `history.csv` (best-effort : n'échoue jamais la commande)."""
    try:
        directory = directory or config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / HISTORY_FILE
        write_header = not path.is_file()
        with path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if write_header:
                writer.writerow(HISTORY_HEADER)
            writer.writerow(entry.as_row())
    except OSError:
        pass  # l'historique ne doit jamais bloquer le contrôle des luminaires


def read_history(limit: int = 20, directory: Path | None = None) -> list[list[str]]:
    """Retourne les `limit` dernières lignes de l'historique (sans l'en-tête)."""
    path = (directory or config_dir()) / HISTORY_FILE
    if not path.is_file():
        return []
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    if rows and rows[0] == HISTORY_HEADER:
        rows = rows[1:]
    return rows[-limit:] if limit > 0 else rows


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
