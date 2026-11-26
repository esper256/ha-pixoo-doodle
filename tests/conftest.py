from pathlib import Path

import pytest_asyncio
from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import HomeAssistant


@pytest_asyncio.fixture
async def core(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    from homeassistant.auth import auth_manager_from_config

    loader.async_setup(hass)
    hass.config.skip_pip = True
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components"
    )
    await bootstrap.async_load_base_functionality(hass)
    hass.auth = await auth_manager_from_config(hass, [], [])
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)
