from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession, web

from custom_components.pixoo_doodle.divoom_client import (
    Client,
    DeviceError,
    InvalidToken,
    Unreachable,
    request,
)
from custom_components.pixoo_doodle.divoom_client.cloud import catalog, discover
from custom_components.pixoo_doodle.divoom_client.models import MODELS


@pytest.mark.asyncio
async def test_http_server():
    async def handle(req):
        payload = await req.json()
        assert payload == {"Command": "Channel/GetIndex"}
        return web.json_response({"error_code": 0, "SelectIndex": 0})

    app = web.Application()
    app.router.add_post("/post", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    try:
        await site.start()
        async with ClientSession() as session:
            client = Client(session, "127.0.0.1", 201)
            client.endpoint = f":{runner.addresses[0][1]}/post"
            assert (await client.command("Channel/GetIndex"))["SelectIndex"] == 0
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("hardware", list(MODELS))
async def test_profiles(hardware):
    client = Client(MagicMock(), "127.0.0.1", hardware, "123")

    async def handler(session, method, url, body):
        assert method == ("GET" if hardware in (510, 511, 512) else "POST")
        assert url.endswith(MODELS[hardware].endpoint)
        if hardware in (90, 92, 400):
            assert body["LocalToken" if hardware == 400 else "DeviceToken"] == 123
        else:
            assert "DeviceToken" not in body and "LocalToken" not in body
        return {
            "Sys/GetBrightness": {"Brightness": 20},
            "Channel/GetOnOffScreen": {"OnOff": 1},
            "Channel/GetIndex": {"SelectIndex": 1},
            "Channel/GetAllConf": {"Brightness": 20},
        }[body["Command"]]

    with patch(
        "custom_components.pixoo_doodle.divoom_client.request", side_effect=handler
    ):
        assert (await client.probe())["Brightness"] == 20
    with patch.object(client, "command", AsyncMock(return_value={"error_code": 0})):
        if hardware != 400:
            with pytest.raises(DeviceError):
                await client.state()


@pytest.mark.asyncio
async def test_missing_token():
    client = Client(MagicMock(), "127.0.0.1", 90)
    with pytest.raises(InvalidToken):
        await client.probe()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,error", [(401, InvalidToken), (404, Unreachable), (200, Unreachable)]
)
async def test_http_errors(status, error):
    session = MagicMock()
    response = session.request.return_value.__aenter__.return_value
    response.status = status
    response.json.side_effect = ValueError()
    with pytest.raises(error):
        await request(session, "POST", "http://example.test", {})


@pytest.mark.asyncio
async def test_cloud():
    with patch(
        "custom_components.pixoo_doodle.divoom_client.cloud.request",
        new_callable=AsyncMock,
    ) as req:
        req.return_value = {}
        with pytest.raises(DeviceError):
            await discover(MagicMock())
        row = {"DevicePrivateIP": "127.0.0.1", "DeviceId": 2}
        req.return_value = {"DeviceList": [None, {}, row]}
        assert await discover(MagicMock()) == [row]
        for kind in ("faces", "types", "fonts"):
            await catalog(MagicMock(), kind, "Social", 2)
