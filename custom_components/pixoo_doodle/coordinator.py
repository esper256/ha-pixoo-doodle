"""Entry lifetime, polling and shared device state."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from homeassistant.helpers.update_coordinator import UpdateFailedUnreachable
except ImportError:  # Introduced in Core 2026.12
    UpdateFailedUnreachable = UpdateFailed
from PIL import Image
from .divoom_client import Client, DeviceError, InvalidToken, Json, Unreachable

DOMAIN = "pixoo_doodle"
LOGGER = logging.getLogger(__name__)
type PixooConfigEntry = ConfigEntry[RuntimeData]


class RuntimeData(DataUpdateCoordinator[Json]):
    def __init__(self, hass: HomeAssistant, entry: PixooConfigEntry):
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get("poll_interval", 30)),
        )
        self.entry = entry
        self.client = Client(
            async_get_clientsession(hass),
            entry.data["host"],
            entry.data["hardware"],
            entry.data.get("token"),
            entry.options.get("push_throttle", 1),
        )
        self.canvas = (
            Image.new("RGB", self.client.model.resolution)
            if self.client.model.canvas
            else None
        )
        self.canvas_lock = asyncio.Lock()
        self.preview: bytes | None = None
        self.preview_time: datetime | None = None
        self.assumed: Json = {}

    def issue(self, key: str) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{self.entry.entry_id}_{key}",
            config_entry_id=self.entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=key,
        )

    async def _async_setup(self) -> None:
        try:
            await self.client.probe()
        except InvalidToken as exc:
            raise ConfigEntryAuthFailed from exc
        except DeviceError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def _async_update_data(self) -> Json:
        try:
            previous = self.client.endpoint
            try:
                state = await self.client.state()
            except Unreachable:
                state = await self.client.probe()
            if previous != self.client.endpoint:
                self.issue("endpoint_changed")
            return self.assumed | state
        except InvalidToken as exc:
            raise ConfigEntryAuthFailed from exc
        except Unreachable as exc:
            raise UpdateFailedUnreachable(str(exc)) from exc
        except DeviceError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def write(
        self, command: str, fields: Json, assume: Json | None = None
    ) -> None:
        try:
            await self.client.command(command, **fields)
        except DeviceError as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="device_error"
            ) from exc
        self.assumed.update(assume or {})
        await self.async_request_refresh()
