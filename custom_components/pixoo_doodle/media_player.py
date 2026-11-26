"""Artwork playback; the user starts every rotation explicitly."""

import asyncio
import logging
import random
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

from aiohttp import ClientError
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature as Feature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from PIL import Image

from .coordinator import DOMAIN, PixooConfigEntry, RuntimeData
from .divoom_client import DeviceError
from .entity import PixooEntity
from .gallery import GalleryError, MissingArtwork
from .playlists import PREFIX, Track, invalid_mix
from .services import draw, load_media

PARALLEL_UPDATES = 0
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if entry.runtime_data.client.model.canvas:
        async_add_entities([ArtPlayer(entry.runtime_data)])


class ArtPlayer(PixooEntity, MediaPlayerEntity):
    _attr_state = MediaPlayerState.IDLE
    _attr_supported_features = (
        Feature.PLAY_MEDIA
        | Feature.PLAY
        | Feature.PAUSE
        | Feature.STOP
        | Feature.NEXT_TRACK
        | Feature.SELECT_SOURCE
        | Feature.SHUFFLE_SET
    )
    _attr_shuffle = False
    _attr_media_content_type = MediaType.IMAGE

    def __init__(self, runtime: RuntimeData) -> None:
        super().__init__(runtime, "art_player")
        self._ordered: list[Track] = []
        self._queue: list[Track] = []
        self._index = -1
        self._seconds = 60
        self._cancel_timer: Callable[[], None] | None = None
        self._job: asyncio.Task[None] | None = None
        self._prefix = PREFIX + runtime.entry.entry_id + "/"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.stop_rotation = self.stop_rotation

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.stop_rotation = None
        self._cancel()
        await super().async_will_remove_from_hass()

    @property
    def source_list(self) -> list[str]:
        return sorted(self.coordinator.playlists.saved)

    def _cancel(self) -> None:
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._job and not self._job.done():
            self._job.cancel()
        self._job = None

    @callback
    def stop_rotation(self) -> None:
        self._cancel()
        self._queue = []
        self._ordered = []
        self._index = -1
        self._attr_source = None
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_content_id = None
        self._attr_media_image_url = None
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _run(self, work: Coroutine[Any, Any, None]) -> None:
        self._cancel()
        task = self.coordinator.entry.async_create_background_task(
            self.hass, work, "Pixoo art playback", eager_start=False
        )
        self._job = task
        try:
            await task
        except asyncio.CancelledError:
            if (current := asyncio.current_task()) and current.cancelling():
                raise
        except (
            HomeAssistantError,
            DeviceError,
            ClientError,
            TimeoutError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ) as exc:
            self._attr_state = (
                MediaPlayerState.PAUSED if self._queue else MediaPlayerState.IDLE
            )
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="playback_failed"
            ) from exc
        finally:
            if self._job is task:
                self._job = None

    def _schedule(self) -> None:
        if len(self._queue) > 1:
            self._cancel_timer = async_call_later(
                self.hass, self._seconds, self._advance
            )

    async def _advance(self, now: datetime) -> None:
        self._cancel_timer = None
        if self.state != MediaPlayerState.PLAYING:
            return
        try:
            await self.async_media_next_track()
        except HomeAssistantError as exc:
            LOGGER.warning("Art rotation paused: %s", exc)

    async def _show(self) -> None:
        r = self.coordinator
        offline = False
        for offset in range(1, len(self._queue) + 1):
            i = (self._index + offset) % len(self._queue)
            track = self._queue[i]
            if track.artwork:
                if offline and not r.gallery.cached(track.artwork):
                    continue
                try:
                    data = await r.gallery.image(track.artwork)
                except MissingArtwork:
                    continue
                except GalleryError:
                    offline = True
                    continue
            else:
                data = await load_media(r.hass, track.source)
            await draw(r, "play_gif", {"fit": "fit", "dither": False}, media_data=data)
            self._index = i
            self._attr_media_title = track.title
            self._attr_media_artist = track.artwork.artist if track.artwork else None
            self._attr_media_image_url = (
                track.artwork.thumbnail if track.artwork else None
            )
            self._attr_media_content_id = (
                self._prefix + track.source if track.artwork else track.source
            )
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()
            self._schedule()
            return
        raise GalleryError("No available artwork")

    async def _start(self, source: str) -> None:
        runtime = self.coordinator
        name = None
        seconds = 60
        if source.startswith(self._prefix):
            source = source[len(self._prefix) :]
        if source.startswith("playlist/"):
            name = unquote(source[9:])
            if name not in runtime.playlists.saved:
                raise invalid_mix()
            mix = runtime.playlists.saved[name]
            sources = mix["items"]
            seconds = mix["seconds"]
        else:
            sources = [source]
        queue = await runtime.playlists.expand(
            sources, runtime.gallery, runtime.client.model.resolution[0]
        )
        self._ordered = queue.copy()
        if self.shuffle:
            random.shuffle(queue)
        self._queue, self._index, self._seconds = queue, -1, seconds
        self._attr_source = name
        await self._show()

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        await self._run(self._start(media_id))

    async def async_select_source(self, source: str) -> None:
        await self.async_play_media(
            MediaType.PLAYLIST, "playlist/" + quote(source, safe="")
        )

    async def async_media_next_track(self) -> None:
        if self._queue:
            await self._run(self._show())

    async def async_media_pause(self) -> None:
        self._cancel()
        if self._queue:
            self._attr_state = MediaPlayerState.PAUSED
            self.async_write_ha_state()

    async def async_media_play(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            return
        if self._queue and self._index >= 0:
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()
            self._schedule()
        elif self._queue:
            await self.async_media_next_track()
        elif self.source_list:
            await self.async_select_source(self.source_list[0])

    async def async_media_stop(self) -> None:
        self.stop_rotation()

    async def async_set_shuffle(self, shuffle: bool) -> None:
        self._attr_shuffle = shuffle
        if self._queue:
            current = self._queue[self._index] if self._index >= 0 else None
            self._queue = self._ordered.copy()
            if shuffle:
                random.shuffle(self._queue)
            if current:
                self._index = self._queue.index(current)
        self.async_write_ha_state()
