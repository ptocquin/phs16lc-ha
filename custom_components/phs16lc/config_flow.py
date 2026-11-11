"""Config flow de l'intégration PHS16-LC : choix du port série et des réglages."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PORT
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
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"PHS16-LC {port}", data=user_input)

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
