from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.pixoo_doodle.config_flow import ConfigFlow, identity
from custom_components.pixoo_doodle.divoom_client import DeviceError, InvalidToken

ROW = {
    "DeviceMac": "02:00:00:00:00:01",
    "DeviceId": 1,
    "DevicePrivateIP": "127.0.0.1",
    "Hardware": 201,
}
MODULE = "custom_components.pixoo_doodle.config_flow."


@pytest.fixture
def flow(core):
    flow = ConfigFlow()
    flow.hass = core
    flow.context = {"source": "user"}
    flow.flow_id = "test"
    with patch(MODULE + "async_get_clientsession"):
        yield flow


@pytest.mark.asyncio
async def test_manual(flow):
    assert (await flow.async_step_user())["type"] == "menu"
    assert (await flow.async_step_manual())["step_id"] == "manual"
    assert (await flow.async_step_manual({"host": "invalid"}))["errors"][
        "base"
    ] == "invalid_host"
    with (
        patch(MODULE + "request", side_effect=DeviceError),
        patch(MODULE + "discover", side_effect=DeviceError),
    ):
        assert (await flow.async_step_manual({"host": "127.0.0.1"}))["errors"][
            "base"
        ] == "cloud_unreachable"
    with (
        patch(MODULE + "request", return_value={}),
        patch(MODULE + "discover", return_value=[]),
    ):
        assert (await flow.async_step_manual({"host": "127.0.0.1"}))["errors"][
            "base"
        ] == "identity_missing"
    with (
        patch(MODULE + "request", return_value=ROW),
        patch(MODULE + "Client.probe", new_callable=AsyncMock),
    ):
        assert (await flow.async_step_manual({"host": "127.0.0.1"}))[
            "type"
        ] == "create_entry"


@pytest.mark.asyncio
async def test_discover(flow):
    with patch(MODULE + "discover", side_effect=DeviceError):
        assert (await flow.async_step_cloud())["reason"] == "cloud_unreachable"
    with patch(MODULE + "discover", return_value=[]):
        assert (await flow.async_step_cloud())["reason"] == "no_devices"
    with patch(MODULE + "discover", return_value=[ROW]):
        assert (await flow.async_step_cloud())["step_id"] == "cloud"
    with patch(MODULE + "Client.probe", side_effect=DeviceError):
        assert (await flow.async_step_cloud({"device": identity(ROW)}))[
            "reason"
        ] == "cannot_connect"
    with (
        patch.object(
            flow,
            "_abort_if_unique_id_configured",
            side_effect=AbortFlow("already_configured"),
        ),
        pytest.raises(AbortFlow),
    ):
        await flow._identify(ROW)


@pytest.mark.asyncio
async def test_tokens(flow):
    assert identity({"DeviceId": 1}) == "1"
    for row in [{}, {"Hardware": -1}]:
        assert (await flow._identify(row))["reason"] == "unknown_hardware"
    assert (await flow._identify({**ROW, "Hardware": 90}))["step_id"] == "token"
    with patch(MODULE + "Client.probe", side_effect=InvalidToken):
        assert (await flow.async_step_token({"token": "123"}))["errors"][
            "base"
        ] == "invalid_auth"
    with patch(MODULE + "Client.probe", return_value={}):
        assert (await flow.async_step_token({"token": "456"}))["data"]["token"] == "456"


@pytest.mark.asyncio
async def test_reconfigure_reauth(flow):
    entry = MagicMock(data={"host": "127.0.0.1", "hardware": 90, "token": "123"})
    with patch.object(flow, "_get_reconfigure_entry", return_value=entry):
        assert (await flow.async_step_reconfigure())["step_id"] == "reconfigure"
    with patch.object(flow, "_get_reauth_entry", return_value=entry):
        assert (await flow.async_step_reauth({}))["step_id"] == "token"
    with (
        patch.object(flow, "_abort_if_unique_id_mismatch") as verify,
        patch.object(
            flow, "async_update_reload_and_abort", return_value={"type": "abort"}
        ),
        patch(MODULE + "Client.probe", return_value={}),
    ):
        assert (await flow._identify({**ROW, "Hardware": 90}))["type"] == "abort"
        verify.assert_called_once()
        assert flow.pending["token"] == "123"
    assert (
        await flow.async_step_dhcp(
            DhcpServiceInfo(ip="127.0.0.1", hostname="panel", macaddress="020000000002")
        )
    )["reason"] == "unknown_hardware"


@pytest.mark.asyncio
async def test_options(flow):
    options = flow.async_get_options_flow(None)
    with patch.object(type(options), "config_entry", MagicMock(options={})):
        assert (await options.async_step_init())["step_id"] == "init"
    assert (await options.async_step_init({"poll_interval": 10}))["data"][
        "poll_interval"
    ] == 10
