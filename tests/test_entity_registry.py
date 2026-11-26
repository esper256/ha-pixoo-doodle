"""Verify what a fresh installation registers, including disabled entities."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.pixoo_doodle.coordinator import DOMAIN
from custom_components.pixoo_doodle.divoom_client import Client
from custom_components.pixoo_doodle.entity import CHANNELS


@pytest.mark.parametrize(
    ("hardware", "pixoo", "mirror", "restart", "buzzer", "firmware"),
    [
        (201, True, True, False, True, None),
        (90, True, True, True, True, None),
        (92, True, True, True, True, None),
        (96, True, True, True, True, 90109),
        (96, True, True, True, False, 90108),
        (400, False, True, True, True, None),
        (402, False, True, True, True, None),
        (510, False, True, True, False, None),
        (511, False, True, True, False, None),
        (512, False, True, True, False, None),
        (530, False, False, False, False, None),
    ],
)
async def test_registered_entities(
    core, hardware, pixoo, mirror, restart, buzzer, firmware
):
    entry = ConfigEntry(
        domain=DOMAIN,
        title="Panel",
        data={
            "host": "127.0.0.1",
            "hardware": hardware,
            "mac": "020000000001",
            "token": "123",
        },
        options={},
        source="user",
        unique_id="panel",
        version=1,
        minor_version=1,
        discovery_keys={},
        subentries_data=[],
    )
    replies = {
        "Channel/GetAllConf": {"Brightness": 20},
        "Channel/GetIndex": {"SelectIndex": 0},
        "Sys/GetBrightness": {"Brightness": 20},
        "Channel/GetOnOffScreen": {"OnOff": 1},
        "Device/GetHardwareVersion": {
            "Hardware": hardware,
            "FirmwareVersion": firmware,
        },
    }
    expected = {
        "display": ("light", None),
        "brightness": ("number", None),
        "hour24": ("switch", "config"),
        **{
            k: ("sensor", "diagnostic")
            for k in ("firmware", "resolution", "hardware", "endpoint")
        },
    }
    if mirror:
        expected["mirror"] = ("switch", "config")
    if restart:
        expected["reboot"] = ("button", "config")
    if buzzer:
        expected["buzzer"] = ("button", "diagnostic")
    if pixoo:
        expected.update(
            {
                k: ("select", None)
                for k in (
                    "channel",
                    "cloud_feed",
                    "clock_face",
                    "custom_page",
                    "visualizer",
                )
            }
        )
        expected.update(
            rotation=("select", "config"),
            current_channel=("sensor", "diagnostic"),
            preview=("image", None),
            art_player=("media_player", None),
        )
    with patch.object(
        Client, "command", AsyncMock(side_effect=lambda cmd, **kw: replies[cmd].copy())
    ):
        await core.config_entries.async_add(entry)
        assert entry.state == ConfigEntryState.LOADED
        (device,) = dr.async_entries_for_config_entry(
            dr.async_get(core), entry.entry_id
        )
        assert device.manufacturer == "Divoom" and device.hw_version == str(hardware)
        rows = er.async_entries_for_config_entry(er.async_get(core), entry.entry_id)
        assert len(rows) == len(expected)
        observed = {}
        for row in rows:
            key = row.translation_key
            assert row.device_id == device.id and row.unique_id == f"panel_{key}"
            assert row.has_entity_name
            assert row.disabled_by == (
                "integration" if key in {"endpoint", "buzzer", "reboot"} else None
            )
            assert row.original_device_class == {
                "reboot": "restart",
                "current_channel": "enum",
            }.get(key)
            observed[key] = (row.domain, row.entity_category)
        assert observed == expected
        if pixoo:
            channel = next(r for r in rows if r.translation_key == "current_channel")
            assert core.states.get(channel.entity_id).attributes["options"] == CHANNELS
        assert await core.config_entries.async_unload(entry.entry_id)
