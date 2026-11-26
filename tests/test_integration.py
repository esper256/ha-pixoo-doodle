"""Exercise actual Core entry setup, actions, platforms and teardown."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import ServiceValidationError

from custom_components.pixoo_doodle.coordinator import DOMAIN
from custom_components.pixoo_doodle.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.pixoo_doodle.divoom_client import Client

FIXTURE = json.loads((Path(__file__).parent / "fixtures/pixoo16.json").read_text())


@pytest.mark.asyncio
async def test_lifecycle(core):
    entry = config_entries.ConfigEntry(
        domain=DOMAIN,
        title="Pixoo 16",
        data={"host": "127.0.0.1", "hardware": 201, "mac": "020000000001"},
        options={},
        source="user",
        unique_id="020000000001",
        version=1,
        minor_version=1,
        discovery_keys={},
        subentries_data=[],
    )

    async def command(cmd, **kw):
        return FIXTURE.get(cmd, {"error_code": 0}).copy()

    with patch.object(Client, "command", AsyncMock(side_effect=command)):
        await core.config_entries.async_add(entry)
        assert entry.state == config_entries.ConfigEntryState.LOADED
        states = {s.domain for s in core.states.async_all()}
        assert {"light", "select", "switch", "sensor", "number", "image"} <= states

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(core)
        snapshot = {
            entity.unique_id.removeprefix(entry.unique_id + "_"): core.states.get(
                entity.entity_id
            ).state
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if entity.disabled_by is None
        }
        assert snapshot == {
            "display": "unknown",
            "art_player": "idle",
            "brightness": "20",
            "channel": "faces",
            "custom_page": "unknown",
            "cloud_feed": "unknown",
            "rotation": "0",
            "visualizer": "unknown",
            "clock_face": "84",
            "mirror": "off",
            "hour24": "off",
            "hardware": "201",
            "firmware": "unknown",
            "resolution": "16×16",
            "current_channel": "faces",
            "preview": "unknown",
        }

        async def action(name, **args):
            return await core.services.async_call(
                DOMAIN,
                name,
                {"config_entry_id": entry.entry_id, **args},
                blocking=True,
                return_response=name.startswith("get_"),
            )

        await action("fill", color="#ff0000", commit=False)
        assert entry.runtime_data.preview is None
        await action("draw_pixels", points=[[0, 0]], color="#0000ff")
        assert (await action("get_canvas"))[entry.entry_id]["png"].startswith("iVBOR")
        assert entry.runtime_data.canvas.getpixel((0, 0)) == (0, 0, 255)
        with pytest.raises(ServiceValidationError):
            await action("draw_pixels", points=[[16, 0]])
        diagnostic = await async_get_config_entry_diagnostics(core, entry)
        assert "127.0.0.1" not in str(diagnostic)
        assert await core.config_entries.async_unload(entry.entry_id)


async def test_actions_by_device(core, tmp_path):
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import device_registry as dr
    from PIL import Image

    from custom_components.pixoo_doodle.divoom_client import DeviceError

    entry = config_entries.ConfigEntry(
        domain=DOMAIN,
        title="Display",
        data={"host": "127.0.0.1", "hardware": 201},
        options={},
        source="user",
        unique_id="test-device",
        version=1,
        minor_version=1,
        discovery_keys={},
        subentries_data=[],
    )
    with patch.object(
        Client,
        "command",
        AsyncMock(
            side_effect=lambda cmd, **kw: FIXTURE.get(cmd, {"error_code": 0}).copy()
        ),
    ):
        await core.config_entries.async_add(entry)
        device = dr.async_get(core).async_get_device_by_identifier(
            (DOMAIN, "test-device"), entry.entry_id
        )
        path = tmp_path / "sample.png"
        Image.new("RGB", (9, 3), "red").save(path)
        core.config.allowlist_external_dirs.add(str(tmp_path))
        call = core.services.async_call
        result = await call(
            DOMAIN,
            "show_image",
            {"device_id": device.id, "source": str(path)},
            blocking=True,
            return_response=True,
        )
        assert result[entry.entry_id]["png"]
        for target in (
            {},
            {"device_id": "missing"},
            {"config_entry_id": "missing"},
            {"config_entry_id": entry.entry_id, "device_id": [device.id]},
        ):
            with pytest.raises(ServiceValidationError) as err:
                await call(DOMAIN, "clear", target, blocking=True)
            assert err.value.translation_key == "invalid_target"
        with (
            patch.object(Client, "push", side_effect=DeviceError),
            pytest.raises(HomeAssistantError) as err,
        ):
            await call(DOMAIN, "clear", {"device_id": device.id}, blocking=True)
        assert err.value.translation_key == "device_error"
        await core.config_entries.async_unload(entry.entry_id)
