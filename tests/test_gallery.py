import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.pixoo_doodle.gallery import (
    PAGE,
    Artwork,
    Gallery,
    GalleryError,
    parse_catalog,
    public_url,
)
from custom_components.pixoo_doodle.playlists import Playlists, reference


def test_catalog():
    data = {
        "artists": [{"id": 1, "name": "Art"}],
        "works": [
            None,
            {},
            {"id": "1", "authorId": "1", "gif": "http://localhost/image.gif"},
            {"id": "2", "authorId": 1, "canvas": "16", "gif": "asset:test.gif"},
        ],
    }
    art = parse_catalog(
        json.dumps(data).encode(), "https://divoom.com/assets/catalog.json"
    )["2"]
    assert art.url == "https://divoom.com/assets/test.gif" and art.artist == "Art"
    for invalid in [None, [], {"works": []}, {"works": [], "artists": None}]:
        with pytest.raises(GalleryError):
            parse_catalog(json.dumps(invalid).encode(), PAGE)
    for url in ("", "http://divoom.com/test", "https://divoom.com.example.org/image"):
        with pytest.raises(GalleryError):
            public_url(url, PAGE)


async def test_gallery_cache(monkeypatch):
    gallery = Gallery(MagicMock())
    art = Artwork("1", "A", "2", "Artist", 16, "https://divoom.com/1.gif", "")
    other = Artwork("2", "B", "3", "Artist", 16, "https://divoom.com/2.gif", "")
    monkeypatch.setattr("custom_components.pixoo_doodle.gallery.CACHE_BYTES", 4)
    with patch.object(gallery, "fetch", AsyncMock(return_value=b"123")) as fetch:
        assert await gallery.image(art) == await gallery.image(art)
        await gallery.image(other)
        assert gallery.cached(other) and not gallery.cached(art)
        assert fetch.await_count == 2
    with patch.object(gallery, "fetch", side_effect=GalleryError):
        with pytest.raises(GalleryError):
            await gallery.works()
        gallery._works = {art.id: art}
        assert await gallery.works() == {art.id: art}


async def test_bounded_fetch():
    session = MagicMock()
    gallery = Gallery(session)
    response = session.get.return_value.__aenter__.return_value
    response.status = 200

    async def chunks(_):
        yield b"123"
        yield b"45"

    response.content.iter_chunked = chunks
    assert await gallery.fetch(PAGE, 5) == b"12345"
    with pytest.raises(GalleryError):
        await gallery.fetch(PAGE, 4)
    response.status = 404
    with pytest.raises(GalleryError):
        await gallery.fetch(PAGE, 5)
    session.get.return_value.__aenter__.side_effect = TimeoutError
    with pytest.raises(GalleryError):
        await gallery.fetch(PAGE, 5)


async def test_invalid_edits(core):
    library = Playlists(core, "test")
    for source in (
        "media-source://pixoo_doodle/entry",
        "artist/nope",
        "folder:/etc",
        "playlist/Nested",
    ):
        with pytest.raises(ServiceValidationError):
            reference(source)
    for name, items in [("A/B", ["artist/1"]), ("OK", []), ("none", None)]:
        with pytest.raises(ServiceValidationError):
            await library.edit(name, items)
    with pytest.raises(ServiceValidationError):
        await library.expand([], MagicMock(), 16)
    with (
        patch.object(library.store, "async_save", side_effect=OSError),
        pytest.raises(OSError),
    ):
        await library.edit("Mix", ["artist/1"])
    assert not library.saved
