from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.pixoo_doodle import button, image, light, number, select, switch
from custom_components.pixoo_doodle.coordinator import DOMAIN, RuntimeData
from custom_components.pixoo_doodle.divoom_client import (
    DeviceError,
    InvalidToken,
    Unreachable,
)
from custom_components.pixoo_doodle.divoom_client.models import MODELS
from custom_components.pixoo_doodle.services import dispatch


@pytest.fixture
def runtime(core):
    entry = config_entries.ConfigEntry(
        domain=DOMAIN,
        title="Display",
        data={"host": "127.0.0.1", "hardware": 96},
        options={},
        source="user",
        unique_id="display",
        version=1,
        minor_version=1,
        discovery_keys={},
        subentries_data=[],
    )
    with patch("custom_components.pixoo_doodle.coordinator.async_get_clientsession"):
        r = RuntimeData(core, entry)
    r.data = {"Brightness": 20, "FirmwareVersion": 90109, "CurClockId": 2}
    entry.runtime_data = r
    core.config_entries._entries[entry.entry_id] = entry
    return r


async def test_coordinator(runtime):
    r = runtime
    with (
        patch.object(r.client, "probe", AsyncMock()),
        patch.object(
            r.client,
            "command",
            AsyncMock(return_value={"Software": 90109, "Hardware": 96}),
        ),
    ):
        await r._async_setup()
        assert r.identity["FirmwareVersion"] == 90109
    for err, expected in [
        (InvalidToken, ConfigEntryAuthFailed),
        (DeviceError, UpdateFailed),
        (Unreachable, UpdateFailed),
    ]:
        with patch.object(r.client, "probe", side_effect=err), pytest.raises(expected):
            await r._async_setup()
        with (
            patch.object(r.client, "state", side_effect=err),
            patch.object(r.client, "probe", side_effect=err),
            pytest.raises(expected),
        ):
            await r._async_update_data()
    with (
        patch.object(r.client, "probe", AsyncMock()),
        patch.object(r.client, "command", AsyncMock(return_value={"Hardware": 201})),
        pytest.raises(UpdateFailed),
    ):
        await r._async_setup()

    async def alternate():
        r.client.endpoint = "/post"
        return {"Brightness": 42}

    with (
        patch.object(r.client, "state", side_effect=Unreachable),
        patch.object(r.client, "probe", side_effect=alternate),
    ):
        assert (await r._async_update_data())["Brightness"] == 42
        assert ir.async_get(r.hass).async_get_issue(
            DOMAIN, f"{r.entry.entry_id}_endpoint_changed"
        )
    with (
        patch.object(r.client, "command", side_effect=DeviceError),
        pytest.raises(HomeAssistantError) as exc,
    ):
        await r.write("Channel/SetBrightness", {"Brightness": 20})
    assert exc.value.translation_key == "device_error"


async def test_actions_and_repair(runtime):
    r = runtime
    with patch.object(r, "write", new_callable=AsyncMock) as write:
        for action, args, cmd in [
            ("scoreboard", {"red": 1, "blue": 2}, "Tools/SetScoreBoard"),
            ("stopwatch", {"status": 1}, "Tools/SetStopWatch"),
            ("set_timer", {"minute": 2, "second": 3, "status": 1}, "Tools/SetTimer"),
            ("play_buzzer", {}, "Device/PlayBuzzer"),
            ("select_clock_face", {"clock_id": 2}, "Channel/SetClockSelectId"),
        ]:
            await dispatch(r, action, args)
            assert write.await_args.args[0] == cmd
    with patch.object(
        r.client, "state", return_value={"DeviceId": 123, "Brightness": 20}
    ):
        assert await dispatch(r, "get_config", {}) == {"Brightness": 20}
        await dispatch(r, "refresh", {})
    r.data["FirmwareVersion"] = 90100
    with pytest.raises(ServiceValidationError):
        await dispatch(r, "play_buzzer", {})
    assert ir.async_get(r.hass).async_get_issue(
        DOMAIN, f"{r.entry.entry_id}_old_firmware"
    )
    with (
        patch(
            "custom_components.pixoo_doodle.services.catalog", side_effect=DeviceError
        ),
        pytest.raises(DeviceError),
    ):
        await dispatch(r, "get_fonts", {})
    with patch(
        "custom_components.pixoo_doodle.services.catalog",
        return_value={"DialList": [{"ClockId": 4}]},
    ):
        await dispatch(r, "get_faces", {"dial_type": "Social"})
        assert r.faces == {4}
        assert not ir.async_get(r.hass).async_get_issue(
            DOMAIN, f"{r.entry.entry_id}_cloud_unreachable"
        )
    with pytest.raises(ServiceValidationError):
        await dispatch(r, "get_canvas", {})
    r.client.model = MODELS[530]
    r.canvas = None
    for action in ("get_fonts", "select_clock_face", "play_buzzer", "fill"):
        with pytest.raises(ServiceValidationError):
            await dispatch(r, action, {})


async def test_entity_writes(runtime):
    r = runtime
    with (
        patch.object(r.client, "command", new_callable=AsyncMock) as cmd,
        patch.object(r, "async_request_refresh", AsyncMock()),
    ):
        display = light.Display(r, "display")
        assert display.brightness == 51
        await display.async_turn_on(brightness=128)
        assert cmd.await_args.kwargs == {"Brightness": 50}
        await display.async_turn_off()
        await number.Brightness(r, "brightness").async_set_native_value(32)
        setting = switch.Setting(r, "mirror", "MirrorFlag", "Device/SetMirrorMode")
        await setting.async_turn_on()
        await setting.async_turn_off()
        await select.Control(r, "channel").async_select_option("custom")
        await select.Face(r, "clock_face").async_select_option("4")
        entities = []
        await button.async_setup_entry(r.hass, r.entry, entities.extend)
        await entities[0].async_press()
        assert cmd.await_args.args[0] == "Device/SysReboot"


async def test_native_text(runtime):
    r = runtime
    with (
        patch.object(r.client, "push", AsyncMock()) as push,
        patch.object(r.client, "command", AsyncMock()) as cmd,
    ):
        await dispatch(
            r, "draw_text", {"text": "Hi", "y": 1, "color": "#00ff00", "align": "left"}
        )
        assert push.await_count == 1
        assert cmd.await_args.args == ("Draw/SendHttpText",)
        with patch("homeassistant.components.image.entity.get_async_client"):
            assert await image.Preview(r).async_image() == r.preview


async def test_unreachable_recovery_logs(runtime, caplog):
    import logging

    r = runtime
    with (
        caplog.at_level(logging.INFO, logger=r.logger.name),
        patch.object(r.client, "state", side_effect=Unreachable),
        patch.object(r.client, "probe", side_effect=Unreachable),
    ):
        await r.async_refresh()
        assert not r.last_update_success
        await r.async_refresh()
        with patch.object(r.client, "state", return_value={"Brightness": 20}):
            await r.async_refresh()
        assert r.last_update_success
    messages = [record for record in caplog.records if record.name == r.logger.name]
    assert len(messages) == 2
    assert all(record.levelno == logging.INFO for record in messages)
