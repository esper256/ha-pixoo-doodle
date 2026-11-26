"""Home Assistant Media browser for the public Divoom art gallery."""

from urllib.parse import quote, unquote

from homeassistant.components.media_player import (
    MediaClass,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .coordinator import DOMAIN, RuntimeData
from .gallery import Artwork, GalleryError

PAGE_SIZE = 60


def node(
    path: str,
    title: str,
    cls: MediaClass = MediaClass.DIRECTORY,
    *,
    play: bool = False,
    thumb: str | None = None,
) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=path,
        title=title,
        media_class=cls,
        media_content_type=cls,
        can_play=play,
        can_expand=cls != MediaClass.IMAGE,
        thumbnail=thumb,
        can_search=bool(path) and cls != MediaClass.IMAGE,
    )


def tile(entry_id: str, art: Artwork) -> BrowseMediaSource:
    item = node(
        f"{entry_id}/art/{art.id}",
        f"{art.title} · {art.artist} · {art.size}×{art.size}",
        MediaClass.IMAGE,
        play=True,
        thumb=art.thumbnail,
    )
    item.media_content_type = art.mime
    return item


class ArtSource(MediaSource):
    name = "Pixoo Doodle"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def runtime(self, entry_id: str) -> RuntimeData:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if (
            not entry
            or entry.domain != DOMAIN
            or entry.state != ConfigEntryState.LOADED
            or not entry.runtime_data.client.model.canvas
        ):
            raise Unresolvable("Display unavailable")
        runtime: RuntimeData = entry.runtime_data
        return runtime

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        path = item.identifier or ""
        if not path:
            root = node("", "Pixoo Doodle")
            root.children = [
                node(e.entry_id, e.title)
                for e in self.hass.config_entries.async_entries(DOMAIN)
                if e.state == ConfigEntryState.LOADED
                and e.runtime_data.client.model.canvas
            ]
            return root
        entry_id, _, route = path.partition("/")
        runtime = self.runtime(entry_id)
        if not route:
            root = node(entry_id, runtime.entry.title)
            root.children = [
                node(f"{entry_id}/{key}", title)
                for key, title in (
                    ("artists", "Artists"),
                    ("gallery", "Artwork"),
                    ("playlists", "Playlists"),
                )
            ]
            root.children.append(
                BrowseMediaSource(
                    domain="media_source",
                    identifier="",
                    title="Local media",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaClass.DIRECTORY,
                    can_play=False,
                    can_expand=True,
                )
            )
            return root
        if route == "playlists":
            root = node(path, "Playlists")
            root.children = [
                node(
                    f"{entry_id}/playlist/{quote(n, safe='')}",
                    n,
                    MediaClass.PLAYLIST,
                    play=True,
                )
                for n in sorted(runtime.playlists.saved)
            ]
            return root
        if route.startswith("playlist/"):
            name = unquote(route[9:])
            if name not in runtime.playlists.saved:
                raise Unresolvable("Unknown playlist")
            root = node(path, name, MediaClass.PLAYLIST, play=True)
            tracks = await runtime.playlists.expand(
                runtime.playlists.saved[name]["items"],
                runtime.gallery,
                runtime.client.model.resolution[0],
            )
            root.children = [
                tile(entry_id, t.artwork)
                if t.artwork
                else BrowseMediaSource(
                    domain="media_source",
                    identifier=t.source.removeprefix("media-source://media_source/"),
                    title=t.title,
                    media_class=MediaClass.IMAGE,
                    media_content_type=MediaClass.IMAGE,
                    can_play=True,
                    can_expand=False,
                )
                for t in tracks[:PAGE_SIZE]
            ]
            root.not_shown = max(0, len(tracks) - PAGE_SIZE)
            return root
        route, _, page = route.partition("/page/")
        if page and (not page.isascii() or not page.isdigit() or len(page) > 6):
            raise Unresolvable("Invalid page")
        offset = int(page or 0) * PAGE_SIZE
        works = await self.catalog(runtime)
        size = runtime.client.model.resolution[0]
        if route == "artists":
            artists = sorted(
                {(a.artist, a.artist_id) for a in works.values()},
                key=lambda pair: (pair[0].casefold(), pair[1]),
            )
            children = [
                node(
                    f"{entry_id}/artist/{key}",
                    f"{name} ({key})",
                    MediaClass.ARTIST,
                    play=True,
                )
                for name, key in artists[offset : offset + PAGE_SIZE]
            ]
            total = len(artists)
            title = "Artists"
        elif route == "gallery" or route.startswith("artist/"):
            rows = sorted(
                (
                    a
                    for a in works.values()
                    if route == "gallery" or route == f"artist/{a.artist_id}"
                ),
                key=lambda a: a.size != size,
            )
            if not rows:
                raise Unresolvable("Artist unavailable")
            title = "Artwork" if route == "gallery" else rows[0].artist
            children = [tile(entry_id, a) for a in rows[offset : offset + PAGE_SIZE]]
            total = len(rows)
        else:
            raise Unresolvable("Unknown gallery folder")
        artist = route.startswith("artist/") and not page
        root = node(
            path,
            title,
            MediaClass.ARTIST if artist else MediaClass.DIRECTORY,
            play=artist,
        )
        if offset + PAGE_SIZE < total:
            children.append(
                node(f"{entry_id}/{route}/page/{offset // PAGE_SIZE + 1}", "Next page")
            )
        root.children = children
        return root

    async def catalog(self, runtime: RuntimeData) -> dict[str, Artwork]:
        try:
            return await runtime.gallery.works()
        except GalleryError as exc:
            raise Unresolvable(str(exc)) from exc

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        entry_id, _, route = item.identifier.partition("/")
        works = await self.catalog(self.runtime(entry_id))
        if route.startswith("art/") and (art := works.get(route[4:])):
            return PlayMedia(art.url, art.mime)
        raise Unresolvable("Select artwork to resolve an image")

    async def async_search_media(
        self, item: MediaSourceItem, query: SearchMediaQuery
    ) -> SearchMedia:
        entry_id = (item.identifier or "").split("/", 1)[0]
        runtime = self.runtime(entry_id)
        works = await self.catalog(runtime)
        needle = query.search_query.casefold().strip()
        artists = sorted(
            {
                (a.artist, a.artist_id)
                for a in works.values()
                if needle in a.artist.casefold()
            }
        )
        matches = sorted(
            (
                a
                for a in works.values()
                if needle in a.title.casefold() or needle in a.artist.casefold()
            ),
            key=lambda a: a.size != runtime.client.model.resolution[0],
        )
        results = [
            node(
                f"{entry_id}/artist/{key}",
                f"{name} ({key})",
                MediaClass.ARTIST,
                play=True,
            )
            for name, key in artists[:20]
        ]
        results.extend(tile(entry_id, a) for a in matches[:PAGE_SIZE])
        return SearchMedia(result=results)


async def async_get_media_source(hass: HomeAssistant) -> ArtSource:
    return ArtSource(hass)
