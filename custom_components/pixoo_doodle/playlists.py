"""Per-display named mixes and round-robin source expansion."""

import asyncio
from dataclasses import dataclass
from itertools import zip_longest
from urllib.parse import unquote

from homeassistant.components import media_source
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store

from .divoom_client import Json
from .gallery import Artwork, Gallery

PREFIX = "media-source://pixoo_doodle/"
LOCAL = "media-source://media_source/"


def invalid_mix() -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain="pixoo_doodle", translation_key="invalid_playlist"
    )


def reference(value: str) -> str:
    if value.startswith(PREFIX):
        _, sep, value = value[len(PREFIX) :].partition("/")
        if not sep:
            raise invalid_mix()
    if value.startswith("folder:" + LOCAL) and len(value) > len("folder:" + LOCAL):
        return value
    if value.startswith(LOCAL) and len(value) > len(LOCAL):
        return value
    kind, sep, key = value.partition("/")
    if sep and kind in ("artist", "art") and key.isascii() and key.isdecimal():
        return value
    raise invalid_mix()


@dataclass(frozen=True, slots=True)
class Track:
    source: str
    title: str
    artwork: Artwork | None = None


def store_for(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Json]]:
    return Store(hass, 1, f"pixoo_doodle.{entry_id}.playlists")


class Playlists:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.store = store_for(hass, entry_id)
        self.saved: dict[str, Json] = {}
        self.lock = asyncio.Lock()

    async def load(self) -> None:
        self.saved = await self.store.async_load() or {}

    async def edit(
        self,
        name: str,
        items: list[str] | None,
        seconds: int = 60,
        *,
        append: bool = False,
    ) -> None:
        name = name.strip()
        if not name or len(name) > 80 or "/" in name:
            raise invalid_mix()
        async with self.lock:
            updated = self.saved.copy()
            if items is None:
                if name not in updated:
                    raise invalid_mix()
                del updated[name]
            else:
                sources = [reference(item) for item in items]
                if append and name in updated:
                    sources = list(dict.fromkeys(updated[name]["items"] + sources))
                    seconds = updated[name]["seconds"]
                if not 1 <= len(sources) <= 100 or not 5 <= seconds <= 3600:
                    raise invalid_mix()
                updated[name] = {"items": sources, "seconds": seconds}
            await self.store.async_save(updated)
            self.saved = updated

    async def expand(
        self, sources: list[str], gallery: Gallery, size: int
    ) -> list[Track]:
        groups = []
        for source in sources:
            source = reference(source)
            if source.startswith(LOCAL):
                groups.append([Track(source, unquote(source.rsplit("/", 1)[-1]))])
                continue
            if source.startswith("folder:"):
                node = await media_source.async_browse_media(
                    self.hass, source.removeprefix("folder:")
                )
                nodes = node.children or [] if node.can_expand else [node]
                groups.append(
                    [
                        Track(n.media_content_id, n.title)
                        for n in nodes
                        if n.can_play
                        and (
                            str(n.media_content_type).startswith("image/")
                            or n.media_class == "image"
                        )
                    ][:200]
                )
                continue
            works = await gallery.works()
            kind, key = source.split("/")
            art = [works[key]] if kind == "art" and key in works else []
            if kind == "artist":
                art = sorted(
                    (a for a in works.values() if a.artist_id == key),
                    key=lambda a: a.size != size,
                )[:200]
            groups.append([Track(f"art/{a.id}", a.title, a) for a in art])
        unique: dict[str, Track] = {}
        for row in zip_longest(*groups):
            for track in row:
                if track is not None:
                    unique.setdefault(track.source, track)
        if not unique:
            raise invalid_mix()
        return list(unique.values())
