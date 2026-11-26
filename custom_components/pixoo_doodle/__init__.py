"""Pixoo Doodle integration."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .coordinator import PixooConfigEntry

PLATFORMS = ("light", "number", "select", "sensor", "switch", "button", "image")


def _entry_only_config(config: ConfigType) -> ConfigType:
    from homeassistant.helpers import config_validation as cv

    return cv.config_entry_only_config_schema("pixoo_doodle")(config)


CONFIG_SCHEMA = _entry_only_config


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    from .services import async_setup_services

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PixooConfigEntry) -> None:
    from .coordinator import RuntimeData

    runtime = RuntimeData(hass, entry)
    await runtime.async_config_entry_first_refresh()
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: PixooConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
