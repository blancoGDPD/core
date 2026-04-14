"""Config flow for the Denon RS232 integration."""

from __future__ import annotations

from typing import Any

from denon_rs232 import DenonReceiver
from denon_rs232.models import MODELS
import voluptuous as vol

from homeassistant.components import usb
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_MODEL
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN, LOGGER

OPTION_PICK_MANUAL = "manual"


async def _async_attempt_connect(port: str, model_key: str) -> str | None:
    """Attempt to connect to the receiver at the given port.

    Returns None on success, error on failure.
    """
    model = MODELS[model_key]
    receiver = DenonReceiver(port, model=model)

    try:
        await receiver.connect()
    except (
        # When the port contains invalid connection data
        ValueError,
        # If it is a remote port, and we cannot connect
        ConnectionError,
        OSError,
        TimeoutError,
    ):
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected exception")
        return "unknown"
    else:
        await receiver.disconnect()
        return None


class DenonRS232ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Denon RS232."""

    VERSION = 1

    _model: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_DEVICE] == OPTION_PICK_MANUAL:
                self._model = user_input[CONF_MODEL]
                return await self.async_step_manual()

            self._async_abort_entries_match({CONF_DEVICE: user_input[CONF_DEVICE]})
            error = await _async_attempt_connect(
                user_input[CONF_DEVICE], user_input[CONF_MODEL]
            )
            if not error:
                return self.async_create_entry(
                    title=MODELS[user_input[CONF_MODEL]].name,
                    data={
                        CONF_DEVICE: user_input[CONF_DEVICE],
                        CONF_MODEL: user_input[CONF_MODEL],
                    },
                )
            errors["base"] = error

        ports = await self.hass.async_add_executor_job(get_ports)
        port_options = [
            SelectOptionDict(value=device, label=name) for device, name in ports.items()
        ]
        port_options.append(
            SelectOptionDict(value=OPTION_PICK_MANUAL, label=OPTION_PICK_MANUAL)
        )

        if user_input is None and port_options:
            user_input = {CONF_DEVICE: port_options[0]["value"]}

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_MODEL): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    SelectOptionDict(value=key, label=model.name)
                                    for key, model in MODELS.items()
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                                translation_key="model",
                            )
                        ),
                        vol.Required(CONF_DEVICE): SelectSelector(
                            SelectSelectorConfig(
                                options=port_options,
                                mode=SelectSelectorMode.DROPDOWN,
                                translation_key="device",
                            )
                        ),
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manual port selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_DEVICE: user_input[CONF_DEVICE]})
            error = await _async_attempt_connect(user_input[CONF_DEVICE], self._model)
            if not error:
                return self.async_create_entry(
                    title=MODELS[self._model].name,
                    data={
                        CONF_DEVICE: user_input[CONF_DEVICE],
                        CONF_MODEL: self._model,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_DEVICE): str}),
                user_input or {},
            ),
            errors=errors,
        )


def get_ports() -> dict[str, str]:
    """Get available serial ports keyed by their device path."""
    return {
        port.device: usb.human_readable_device_name(
            port.device,
            port.serial_number,
            port.manufacturer,
            port.description,
            getattr(port, "vid", None),
            getattr(port, "pid", None),
        )
        for port in usb.scan_serial_ports()
    }
