"""Entry lifetime, polling and shared device state."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from homeassistant.helpers.update_coordinator import UpdateFailedUnreachable  # type: ignore[attr-defined]
except ImportError:  # Introduced in Core 2026.12

    class UpdateFailedUnreachable(UpdateFailed):  # type: ignore[no-redef]
        """Compatibility exception for Core 2026.11."""

    def _unreachable_log_level(record: logging.LogRecord) -> bool:
        # Core already suppresses duplicate failure messages and logs recovery.
        if (
            record.levelno == logging.ERROR
            and isinstance(record.args, tuple)
            and any(isinstance(arg, UpdateFailedUnreachable) for arg in record.args)
        ):
            record.levelno = logging.INFO
            record.levelname = "INFO"
        return True

    logging.getLogger(__name__).addFilter(_unreachable_log_level)
from PIL import Image

from .divoom_client import Client, DeviceError, InvalidToken, Json, Unreachable
from .gallery import Gallery
from .playlists import Playlists

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
        self.gallery = Gallery(self.client.session)
        self.playlists = Playlists(hass, entry.entry_id)
        self.stop_rotation: Callable[[], None] | None = None
        self.canvas_lock = asyncio.Lock()
        self.preview: bytes | None = None
        self.preview_time: datetime | None = None
        self.assumed: Json = {}
        self.faces: set[int] = set()
        self.identity: Json = {}

    def firmware_allows(self, minimum: int) -> bool:
        value = self.data.get("FirmwareVersion")
        return value is None or (str(value).isdecimal() and int(value) >= minimum)

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
            if self.client.endpoint != self.client.model.endpoint:
                self.issue("endpoint_changed")
            if self.client.model.endpoint.startswith(":"):
                try:
                    identity = await self.client.command("Device/GetHardwareVersion")
                except InvalidToken:
                    raise
                except DeviceError:
                    identity = {}
                if (
                    hw := identity.get("Hardware")
                ) is not None and hw != self.client.hardware:
                    raise DeviceError("Display hardware changed")
                if fw := identity.get("FirmwareVersion", identity.get("Software")):
                    self.identity["FirmwareVersion"] = fw
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
            return self.identity | self.assumed | state
        except InvalidToken as exc:
            raise ConfigEntryAuthFailed from exc
        except Unreachable as exc:
            raise UpdateFailedUnreachable(str(exc)) from exc
        except DeviceError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def write(
        self, command: str, fields: Json, assume: Json | None = None
    ) -> None:
        if self.stop_rotation and (
            command.startswith(
                (
                    "Channel/SetIndex",
                    "Channel/CloudIndex",
                    "Channel/SetClock",
                    "Channel/SetCustom",
                    "Channel/SetEq",
                    "Tools/",
                )
            )
            or (command == "Channel/OnOffScreen" and fields.get("OnOff") == 0)
        ):
            self.stop_rotation()
        try:
            await self.client.command(command, **fields)
        except DeviceError as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="device_error"
            ) from exc
        self.assumed.update(assume or {})
        await self.async_request_refresh()
