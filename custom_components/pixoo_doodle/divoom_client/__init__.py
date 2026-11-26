"""Asynchronous Divoom LAN transport and paced animation writer."""

import asyncio
from base64 import b64encode
from ipaddress import IPv4Address
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .models import LEGACY, MODERN, MODELS

type Json = dict[str, Any]


class DeviceError(Exception):
    """Device rejected a request or returned a malformed reply."""


class Unreachable(DeviceError):
    """No usable HTTP endpoint answered."""


class InvalidToken(DeviceError):
    """The target requires a valid token."""


async def request(session: ClientSession, method: str, url: str, payload: Json) -> Json:
    try:
        async with session.request(
            method,
            url,
            json=payload,
            timeout=ClientTimeout(total=6),
            allow_redirects=False,
        ) as response:
            if response.status in (401, 403):
                raise InvalidToken
            if response.status != 200:
                raise Unreachable(f"HTTP {response.status}")
            data = await response.json(content_type=None)
    except (ClientError, TimeoutError, ValueError) as exc:
        raise Unreachable("Invalid or missing HTTP response") from exc
    if not isinstance(data, dict):
        raise DeviceError("Expected an object")
    codes = [data[k] for k in ("error_code", "ReturnCode") if k in data]
    if not codes or any(type(c) is not int or c != 0 for c in codes):
        message = str(data.get("ReturnMessage", data.get("error_code", "")))
        if "token" in message.lower():
            raise InvalidToken
        raise DeviceError("Device rejected the request")
    return data


class Client:
    def __init__(
        self,
        session: ClientSession,
        host: str,
        hardware: int,
        token: str | None = None,
        throttle: float = 1,
    ) -> None:
        self.session = session
        self.host = str(IPv4Address(host))
        self.model = MODELS[hardware]
        self.hardware = hardware
        self.token = token
        self.endpoint = self.model.endpoint
        self.lock = asyncio.Lock()
        self.throttle = max(1.0, throttle)
        self._last_send = 0.0
        self._frames = 0
        self._next_id = 0

    async def command(self, command: str, **fields: Any) -> Json:
        if key := self.model.token_field:
            if not self.token:
                raise InvalidToken
            fields[key] = int(self.token) if self.token.isdecimal() else self.token
        return await request(
            self.session,
            self.model.method,
            f"http://{self.host}{self.endpoint}",
            {"Command": command, **fields},
        )

    async def state(self) -> Json:
        match self.model.family:
            case "frame":
                return await self.command("Device/GetHardwareVersion")
            case "astro":
                return {
                    **await self.command("Sys/GetBrightness"),
                    **await self.command("Channel/GetOnOffScreen"),
                }
        config = await self.command("Channel/GetAllConf")
        if self.model.canvas:
            config.update(await self.command("Channel/GetIndex"))
            if "SelectIndex" not in config:
                raise DeviceError("Channel missing in reply")
        return config

    async def probe(self) -> Json:
        original = self.endpoint
        for endpoint in (original, MODERN if original == LEGACY else LEGACY):
            self.endpoint = endpoint
            try:
                return await self.state()
            except InvalidToken:
                raise
            except DeviceError:
                if endpoint != original:
                    self.endpoint = original
                    raise
        raise AssertionError

    async def push(self, frames: list[tuple[bytes, int]]) -> None:
        width, height = self.model.resolution
        if not self.model.canvas or not 1 <= len(frames) <= 40:
            raise ValueError("Unsupported canvas or frame count")
        if any(
            len(rgb) != width * height * 3 or not 10 <= delay <= 60000
            for rgb, delay in frames
        ):
            raise ValueError("Invalid RGB frame or duration")
        async with self.lock:
            if not self._next_id or self._frames + len(frames) > 32:
                await self.command("Draw/ResetHttpGifId")
                self._frames = 0
                self._next_id = 1
            pic_id = self._next_id
            self._next_id = 0  # A cancelled or partial send must restart with a reset.
            loop = asyncio.get_running_loop()
            for offset, (rgb, delay) in enumerate(frames):
                await asyncio.sleep(
                    max(0, self.throttle - (loop.time() - self._last_send))
                )
                self._last_send = loop.time()
                await self.command(
                    "Draw/SendHttpGif",
                    PicID=pic_id,
                    PicOffset=offset,
                    PicNum=len(frames),
                    PicSpeed=delay,
                    PicData=b64encode(rgb).decode("ascii"),
                    **({"PicWidth": width} if self.model.native_text else {}),
                )
                self._frames += 1
            self._next_id = pic_id + 1
