"""Tests de resolve_config_path / recipes_dir_for_entry (montage /config vs /homeassistant).

HA OS 16+ monte la config en `/homeassistant` dans les add-ons, mais le conteneur
core la voit en `/config` : un chemin configuré en `/config/...` doit être résolu
sur `/homeassistant/...` (et inversement) quand il n'existe pas localement.
"""

from __future__ import annotations

from pathlib import Path

from custom_components.phs16lc.const import (
    CONF_RECIPES_DIR,
    recipes_dir_for_entry,
    resolve_config_path,
    scenes_dir_for,
)


class _FakeEntry:
    def __init__(self, data: dict, options: dict | None = None) -> None:
        self.data = data
        self.options = options or {}


def test_resolve_existing_path_returned_as_is(tmp_path: Path) -> None:
    d = tmp_path / "recipes"
    d.mkdir()
    assert resolve_config_path(str(d)) == d


def test_resolve_relative_path_returned_as_is() -> None:
    assert resolve_config_path("recipes/foo") == Path("recipes/foo")


def test_resolve_alias_when_primary_root_missing(tmp_path: Path) -> None:
    """`/config/...` absent mais `/homeassistant/...` présent → résolu sur l'alias."""
    cfg = tmp_path / "config"
    ha = tmp_path / "homeassistant"
    (ha / "phs16lc" / "recipes").mkdir(parents=True)
    roots = (str(cfg), str(ha))
    resolved = resolve_config_path(str(cfg / "phs16lc" / "recipes"), roots=roots)
    assert resolved == ha / "phs16lc" / "recipes"


def test_resolve_alias_reverse_direction(tmp_path: Path) -> None:
    """`/homeassistant/...` absent mais `/config/...` présent → résolu sur /config."""
    cfg = tmp_path / "config"
    ha = tmp_path / "homeassistant"
    (cfg / "phs16lc").mkdir(parents=True)
    roots = (str(cfg), str(ha))
    resolved = resolve_config_path(str(ha / "phs16lc"), roots=roots)
    assert resolved == cfg / "phs16lc"


def test_resolve_prefers_existing_primary_root(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    ha = tmp_path / "homeassistant"
    (cfg / "phs16lc").mkdir(parents=True)
    (ha / "phs16lc").mkdir(parents=True)
    roots = (str(cfg), str(ha))
    assert resolve_config_path(str(cfg / "phs16lc"), roots=roots) == cfg / "phs16lc"


def test_resolve_unknown_when_nothing_exists(tmp_path: Path) -> None:
    roots = (str(tmp_path / "config"), str(tmp_path / "homeassistant"))
    p = str(tmp_path / "config" / "phs16lc" / "recipes")
    assert resolve_config_path(p, roots=roots) == Path(p)


def test_resolve_ignores_unrelated_absolute_path(tmp_path: Path) -> None:
    p = str(tmp_path / "elsewhere")
    assert resolve_config_path(p) == Path(p)


def test_recipes_dir_for_entry_options_over_data(tmp_path: Path) -> None:
    d = tmp_path / "recipes"
    d.mkdir()
    entry = _FakeEntry({CONF_RECIPES_DIR: "/config/phs16lc/recipes"}, {CONF_RECIPES_DIR: str(d)})
    assert recipes_dir_for_entry(entry) == d


def test_recipes_dir_for_entry_falls_back_to_data(tmp_path: Path) -> None:
    d = tmp_path / "recipes"
    d.mkdir()
    entry = _FakeEntry({CONF_RECIPES_DIR: str(d)})
    assert recipes_dir_for_entry(entry) == d


def test_scenes_dir_for_sibling_of_recipes(tmp_path: Path) -> None:
    recipes = tmp_path / "phs16lc" / "recipes"
    scenes = tmp_path / "phs16lc" / "scenes"
    recipes.mkdir(parents=True)
    scenes.mkdir()
    assert scenes_dir_for(recipes) == scenes
