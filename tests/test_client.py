import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pixoo_doodle.divoom_client import (
    Client,
    DeviceError,
    InvalidToken,
    Unreachable,
    request,
)
from custom_components.pixoo_doodle.divoom_client.models import MODERN

FIXTURE = json.loads((Path(__file__).parent / "fixtures/pixoo16.json").read_text())


@pytest.mark.asyncio
async def test_live_fixture():
    client = Client(MagicMock(), "127.0.0.1", 201)
    with patch.object(
        client, "command", AsyncMock(side_effect=lambda c: FIXTURE[c].copy())
    ):
        state = await client.probe()
    assert state["Brightness"] == 20 and state["SelectIndex"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("hardware,width", [(201, 16), (96, 64)])
async def test_push(hardware, width):
    client = Client(MagicMock(), "127.0.0.1", hardware)
    frame = bytes(width * width * 3)
    with (
        patch.object(client, "command", AsyncMock()) as cmd,
        patch.object(asyncio, "sleep", AsyncMock()),
    ):
        await asyncio.gather(
            client.push([(frame, 100)] * 2), client.push([(frame, 100)])
        )
        assert [c.kwargs.get("PicID") for c in cmd.await_args_list] == [None, 1, 1, 2]
        payload = cmd.await_args_list[1].kwargs
        assert base64.b64decode(payload["PicData"]) == frame
        assert ("PicWidth" in payload) == (width == 64)
        with pytest.raises(ValueError):
            await client.push([(b"", 100)])
        with pytest.raises(ValueError):
            await client.push([(frame, 100)] * 41)


@pytest.mark.asyncio
async def test_probe():
    client = Client(MagicMock(), "127.0.0.1", 201)
    with patch.object(client, "state", AsyncMock(side_effect=[Unreachable(), {}])):
        await client.probe()
        assert client.endpoint == MODERN
    with patch.object(client, "state", AsyncMock(side_effect=Unreachable)):
        with pytest.raises(Unreachable):
            await client.probe()
        assert client.endpoint == MODERN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,error",
    [
        ({"ReturnCode": 0}, None),
        ({"error_code": 0, "ReturnCode": 1}, DeviceError),
        ({"error_code": False}, DeviceError),
        ({}, DeviceError),
        ([], DeviceError),
        ({"error_code": "invalid token"}, InvalidToken),
    ],
)
async def test_status(data, error):
    session = MagicMock()
    response = session.request.return_value.__aenter__.return_value
    response.status = 200
    response.json = AsyncMock(return_value=data)
    if error:
        with pytest.raises(error):
            await request(session, "POST", "http://example.test", {})
    else:
        assert await request(session, "POST", "http://example.test", {}) == data
