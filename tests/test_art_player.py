"""Play public gallery fixtures and local files through Core on a simulated panel."""

import asyncio
import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.components import media_source
from homeassistant.components.media_player import SearchMediaQuery
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from PIL import Image

from custom_components.pixoo_doodle.coordinator import DOMAIN
from custom_components.pixoo_doodle.divoom_client import Client
from custom_components.pixoo_doodle.gallery import PAGE, Gallery, GalleryError
from custom_components.pixoo_doodle.playlists import PREFIX, Playlists


def catalog():
    return {
        "artists": [{"id": "11", "name": "Ada"}, {"id": "22", "name": "Ben"}],
        "works": [
            {
                "id": str(i),
                "authorId": str(artist),
                "title": title,
                "canvas": size,
                "gif": f"https://cdn.shopify.com/files/{i}.gif",
            }
            for i, artist, title, size in [
                (1, 11, "Big", 64),
                (2, 11, "Small", 16),
                (3, 22, "Stars", 16),
                (4, 22, "Clouds", 16),
            ]
        ],
    }


@pytest.fixture
async def panel(core, tmp_path):
    core.config.media_dirs = {"local": str(tmp_path)}
    entry = config_entries.ConfigEntry(
        domain=DOMAIN,
        title="Simulated Pixoo",
        data={"host": "127.0.0.1", "hardware": 201},
        options={},
        source="user",
        unique_id="simulated",
        version=1,
        minor_version=1,
        discovery_keys={},
        subentries_data=[],
    )

    def command(cmd, **kw):
        return {
            "Channel/GetAllConf": {"Brightness": 20},
            "Channel/GetIndex": {"SelectIndex": 0},
        }.get(cmd, {"error_code": 0}).copy()

    def fetch(url, limit):
        if url == PAGE:
            return b'<divoom-gallery-v3 data-fallback="//divoom.com/catalog.json">'
        if url.endswith(".json"):
            return json.dumps(catalog()).encode()
        buf = BytesIO()
        Image.new("RGB", (16, 16), "red").save(buf, "GIF")
        return buf.getvalue()

    with (
        patch.object(Client, "command", AsyncMock(side_effect=command)) as wire,
        patch.object(Gallery, "fetch", AsyncMock(side_effect=fetch)) as http,
    ):
        await core.config_entries.async_add(entry)
        assert entry.state == config_entries.ConfigEntryState.LOADED
        entry.runtime_data.client.throttle = 0
        player = er.async_get(core).async_get_entity_id(
            "media_player", DOMAIN, "simulated_art_player"
        )
        try:
            yield entry, player, wire, http
        finally:
            if entry.state == config_entries.ConfigEntryState.LOADED:
                await core.config_entries.async_unload(entry.entry_id)


async def test_browser_and_playlist(core, panel, tmp_path):
    entry, player, wire, http = panel
    prefix = PREFIX + entry.entry_id + "/"
    assert not http.await_count
    assert not any(c.args[0].startswith("Draw/") for c in wire.await_args_list)
    root = await media_source.async_browse_media(core, PREFIX.rstrip("/"))
    assert root.children[0].media_content_id == prefix.rstrip("/")

    async def browse(path):
        return await media_source.async_browse_media(core, prefix + path)

    assert (await browse("artists")).children[0].title == "Ada (11)"
    assert (await browse("gallery")).children[0].title.startswith("Small")
    assert (await browse("artist/11")).children[0].can_play
    search = await media_source.async_search_media(
        core, prefix + "artists", SearchMediaQuery(search_query="ben")
    )
    assert search.result[0].media_content_id == prefix + "artist/22"
    resolved = await media_source.async_resolve_media(core, prefix + "art/2", player)
    assert resolved.mime_type == "image/gif" and resolved.url.endswith("2.gif")

    async def act(service, **fields):
        return await core.services.async_call(
            DOMAIN,
            service,
            {"config_entry_id": entry.entry_id, **fields},
            blocking=True,
        )

    async def play(service, **fields):
        return await core.services.async_call(
            "media_player", service, {"entity_id": player, **fields}, blocking=True
        )

    await act(
        "save_playlist", name="Family mix", items=["artist/11", "artist/22"], seconds=10
    )
    await act(
        "add_to_playlist",
        name="Family mix",
        media={"media_content_id": prefix + "art/2", "media_content_type": "image"},
    )
    local = tmp_path / "art"
    local.mkdir()
    Image.new("RGB", (16, 16), "green").save(local / "family.png")
    await act(
        "add_to_playlist",
        name="Family mix",
        media="folder:media-source://media_source/local/art",
    )
    saved = entry.runtime_data.playlists
    assert saved.saved["Family mix"]["seconds"] == 10
    restored = Playlists(core, entry.entry_id)
    await restored.load()
    assert restored.saved == saved.saved
    mixes = await browse("playlists")
    assert mixes.children[0].title == "Family mix"
    assert len((await browse("playlist/Family%20mix")).children) == 5
    assert (await media_source.async_browse_media(core, prefix.rstrip("/"))).children[
        -1
    ].domain == "media_source"
    await play(
        "play_media",
        media_content_id=mixes.children[0].media_content_id,
        media_content_type="playlist",
    )

    def state():
        return core.states.get(player)

    assert state().state == "playing" and state().attributes["media_title"] == "Small"
    await play("media_next_track")
    assert state().attributes["media_artist"] == "Ben"
    await play("media_next_track")
    assert state().attributes["media_title"] == "family.png"
    await play("media_pause")
    assert state().state == "paused"
    await play("media_play")
    assert state().state == "playing"
    await play("shuffle_set", shuffle=True)
    assert state().attributes["shuffle"]
    await play("media_stop")
    assert state().state == "idle"
    await play("select_source", source="Family mix")
    await act("clear")
    assert state().state == "idle"
    await act("delete_playlist", name="Family mix")
    assert not saved.saved
    assert any(call.args[0] == "Draw/SendHttpGif" for call in wire.await_args_list)


async def test_takeover_during_upload(core, panel):
    entry, entity_id, wire, _ = panel
    prefix = PREFIX + entry.entry_id + "/"
    started = asyncio.Event()

    async def wait_for_stop(*_):
        started.set()
        await asyncio.Future()

    with patch.object(entry.runtime_data.client, "push", side_effect=wait_for_stop):
        first = asyncio.create_task(
            core.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_type": "image",
                    "media_content_id": prefix + "art/2",
                },
                blocking=True,
            )
        )
        await asyncio.wait_for(started.wait(), 2)
        feed = er.async_get(core).async_get_entity_id(
            "select", DOMAIN, "simulated_cloud_feed"
        )
        await core.services.async_call(
            "select",
            "select_option",
            {"entity_id": feed, "option": "subscribed_artists"},
            blocking=True,
        )
        await first
        assert core.states.get(entity_id).state == "idle"
        assert any(
            c.args == ("Channel/CloudIndex",) and c.kwargs == {"Index": 2}
            for c in wire.await_args_list
        )


async def test_timed_and_offline(core, panel):
    entry, entity_id, _, _ = panel
    r = entry.runtime_data
    await r.playlists.edit("test", ["artist/11", "artist/22"], 5)
    from custom_components.pixoo_doodle.media_player import ArtPlayer

    player = ArtPlayer(r)
    player.hass = core
    with (
        patch.object(player, "async_write_ha_state"),
        patch("custom_components.pixoo_doodle.media_player.async_call_later") as timer,
    ):
        await player.async_select_source("test")
        assert timer.call_args.args[1] == 5
        await timer.call_args.args[2](None)
        assert player.media_artist == "Ben"
        with patch.object(r.gallery, "fetch", side_effect=GalleryError):
            await player.async_media_next_track()
            assert player.media_title == "Small"
        await player.async_media_pause()
        count = timer.call_count
        await player._advance(None)
        assert timer.call_count == count
        await player.async_media_stop()
        with pytest.raises(HomeAssistantError):
            await player.async_select_source("missing")
