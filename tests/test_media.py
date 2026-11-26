from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.media_source import PlayMedia
from homeassistant.exceptions import ServiceValidationError
from PIL import Image

from custom_components.pixoo_doodle.services import load_media


async def test_path(core, tmp_path):
    path = tmp_path / "input.png"
    Image.new("RGB", (12, 12)).save(path)
    with pytest.raises(ServiceValidationError):
        await load_media(core, str(path))
    core.config.allowlist_external_dirs.add(str(tmp_path))
    assert (await load_media(core, str(path))).startswith(b"\x89PNG")
    with pytest.raises(ServiceValidationError):
        await load_media(core, "relative.png")
    core.config.media_dirs = {"local": str(tmp_path)}
    with patch(
        "custom_components.pixoo_doodle.services.media_source.async_resolve_media",
        return_value=PlayMedia("/local/image.png", "image/png", path=path),
    ):
        assert (
            await load_media(core, "media-source://media_source/local/input.png")
            == path.read_bytes()
        )
        with (
            patch("custom_components.pixoo_doodle.services.MAX_BYTES", 1),
            pytest.raises(ServiceValidationError),
        ):
            await load_media(core, "media-source://media_source/local/input.png")
    with (
        patch("custom_components.pixoo_doodle.services.MAX_BYTES", 1),
        pytest.raises(ServiceValidationError),
    ):
        await load_media(core, str(path))


async def test_download(core):
    session = MagicMock()
    response = session.get.return_value.__aenter__.return_value

    async def chunks(_):
        yield b"123"

    response.content.iter_chunked = chunks
    with patch(
        "custom_components.pixoo_doodle.services.async_get_clientsession",
        return_value=session,
    ):
        response.status = 200
        assert await load_media(core, "https://example.test/image") == b"123"
        with (
            patch("custom_components.pixoo_doodle.services.MAX_BYTES", 1),
            pytest.raises(ServiceValidationError),
        ):
            await load_media(core, "https://example.test/image")
        response.status = 404
        with pytest.raises(ServiceValidationError):
            await load_media(core, "https://example.test/image")
