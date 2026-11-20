"""Config flow de l'intégration PHS16-LC : choix du port série et des réglages."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_EXPECTED_SPOTS,
    CONF_FAMILY,
    CONF_POLL_INTERVAL,
    CONF_RECIPES_DIR,
    CONF_RX_PORT,
    DEFAULT_FAMILY,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RECIPES_DIR,
    DOMAIN,
    FAMILY_LABELS,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    entry_value,
)
from .phs16ctl.lumiatec import FAMILIES


def _detected_ports() -> list[SelectOptionDict]:
    """Ports série détectés sur la machine (exécuté en thread, pyserial est bloquant)."""
    from serial.tools import list_ports

    return [
        SelectOptionDict(value=p.device, label=p.description or p.device)
        for p in list_ports.comports()
    ]


def _port_selector(ports: list[SelectOptionDict], default: str) -> SelectSelector:
    """Sélecteur de port série : ports détectés + saisie manuelle (custom_value)."""
    options = list(ports)
    if default and all(p["value"] != default for p in options):
        options.append(SelectOptionDict(value=default, label=default))
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            custom_value=True,  # saisie manuelle si aucun port détecté
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class Phs16lcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Formulaire initial : un port série = une entrée de configuration (un bus)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Étape unique : port série + réglages de polling/dossier recettes."""
        if user_input is not None:
            port = str(user_input[CONF_PORT]).strip()
            rx_port = str(user_input.get(CONF_RX_PORT) or "").strip()
            if rx_port == port:
                rx_port = ""  # identique au port TX => montage à un seul port
            family = str(user_input.get(CONF_FAMILY) or DEFAULT_FAMILY)
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            data = {**user_input, CONF_PORT: port, CONF_RX_PORT: rx_port, CONF_FAMILY: family}
            return self.async_create_entry(
                title=f"{FAMILY_LABELS.get(family, family)} {port}", data=data
            )

        ports = await self.hass.async_add_executor_job(_detected_ports)
        schema = vol.Schema(
            {
                vol.Required(CONF_FAMILY, default=DEFAULT_FAMILY): vol.In(list(FAMILIES)),
                vol.Required(
                    CONF_PORT,
                    default=ports[0]["value"] if ports else "/dev/ttyUSB0",
                ): _port_selector(ports, ""),
                # Montage dual (boîtier fabricant 2x USB-RS485-WE) : port TX ci-dessus,
                # port RX ici. Vide = un seul convertisseur full duplex (TX = RX).
                vol.Optional(CONF_RX_PORT, default=""): str,
                vol.Required(CONF_EXPECTED_SPOTS, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
                ),
                vol.Required(CONF_RECIPES_DIR, default=DEFAULT_RECIPES_DIR): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> Phs16lcOptionsFlow:
        return Phs16lcOptionsFlow()


class Phs16lcOptionsFlow(OptionsFlow):
    """Modifie port / rx_port / expected_spots / poll_interval / recipes_dir à chaud (B3).

    La sauvegarde déclenche le update listener enregistré dans __init__.py,
    qui recharge l'entrée : nouveau coordinator, et nouveau port ouvert si le
    port a changé (l'ancien est fermé au déchargement). Le unique_id (le port)
    et le titre de l'entrée suivent le changement de port, pour continuer à
    bloquer un doublon sur le même port physique.
    """

    async def async_step_init(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        if user_input is not None:
            port = str(user_input[CONF_PORT]).strip()
            rx_port = str(user_input.get(CONF_RX_PORT) or "").strip()
            if rx_port == port:
                rx_port = ""  # identique au port TX => montage à un seul port
            if port != entry.unique_id:
                conflict = next(
                    (
                        e
                        for e in self.hass.config_entries.async_entries(DOMAIN)
                        if e.entry_id != entry.entry_id and e.unique_id == port
                    ),
                    None,
                )
                if conflict is not None:
                    schema = await self._build_schema(port, rx_port)
                    return self.async_show_form(
                        step_id="init", data_schema=schema, errors={"base": "already_configured"}
                    )
                # Le unique_id (le port) et le titre sont resynchronisés dans
                # _async_update_listener (après sauvegarde des options) : un
                # second entry sur ce port restera bloqué au config flow.
            return self.async_create_entry(
                data={**user_input, CONF_PORT: port, CONF_RX_PORT: rx_port}
            )
        schema = await self._build_schema(
            str(entry_value(entry, CONF_PORT)), str(entry_value(entry, CONF_RX_PORT) or "")
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def _build_schema(self, default_port: str, default_rx_port: str) -> vol.Schema:
        """Schéma de l'options flow, pré-rempli avec les valeurs effectives courantes."""
        ports = await self.hass.async_add_executor_job(_detected_ports)
        current = {**self.config_entry.data, **self.config_entry.options}
        return vol.Schema(
            {
                vol.Required(
                    CONF_FAMILY, default=str(current.get(CONF_FAMILY, DEFAULT_FAMILY))
                ): vol.In(list(FAMILIES)),
                vol.Required(
                    CONF_PORT,
                    default=default_port or (ports[0]["value"] if ports else "/dev/ttyUSB0"),
                ): _port_selector(ports, default_port),
                # Montage dual (boîtier fabricant 2x USB-RS485-WE) : port RX ici (B3).
                # suggested_value (et PAS default=) : quand le champ est vidé côté
                # frontend, la clé est omise à la soumission — avec un default=
                # voluptuous réinjecterait l'ancienne valeur et on ne pourrait
                # jamais repasser en montage à un seul port (bug prod 2026-11-20).
                vol.Optional(CONF_RX_PORT, description={"suggested_value": default_rx_port}): str,
                vol.Required(
                    CONF_EXPECTED_SPOTS, default=int(current[CONF_EXPECTED_SPOTS])
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
                vol.Required(CONF_POLL_INTERVAL, default=int(current[CONF_POLL_INTERVAL])): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
                ),
                vol.Required(CONF_RECIPES_DIR, default=str(current[CONF_RECIPES_DIR])): str,
            }
        )
