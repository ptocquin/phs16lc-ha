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
    CONF_POLL_INTERVAL,
    CONF_RECIPES_DIR,
    CONF_RX_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RECIPES_DIR,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


def _detected_ports() -> list[SelectOptionDict]:
    """Ports série détectés sur la machine (exécuté en thread, pyserial est bloquant)."""
    from serial.tools import list_ports

    return [
        SelectOptionDict(value=p.device, label=p.description or p.device)
        for p in list_ports.comports()
    ]


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
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            data = {**user_input, CONF_PORT: port, CONF_RX_PORT: rx_port}
            return self.async_create_entry(title=f"PHS16-LC {port}", data=data)

        ports = await self.hass.async_add_executor_job(_detected_ports)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORT,
                    default=ports[0]["value"] if ports else "/dev/ttyUSB0",
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ports,
                        custom_value=True,  # saisie manuelle si aucun port détecté
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
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
    """Modifie expected_spots / poll_interval / recipes_dir sans recréer l'entrée.

    La sauvegarde déclenche le update listener enregistré dans __init__.py,
    qui recharge l'entrée (nouveau coordinator avec le nouvel intervalle).
    """

    async def async_step_init(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXPECTED_SPOTS, default=int(current[CONF_EXPECTED_SPOTS])
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
                vol.Required(CONF_POLL_INTERVAL, default=int(current[CONF_POLL_INTERVAL])): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
                ),
                vol.Required(CONF_RECIPES_DIR, default=str(current[CONF_RECIPES_DIR])): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
