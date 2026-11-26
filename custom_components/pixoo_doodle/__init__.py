"""Pixoo Doodle integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from .coordinator import PixooConfigEntry, RuntimeData

PLATFORMS = ("light", "number", "select", "sensor", "switch", "button", "image")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    from .services import async_setup_services

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PixooConfigEntry) -> None:
    runtime = RuntimeData(hass, entry)
    await runtime.async_config_entry_first_refresh()
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: PixooConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
