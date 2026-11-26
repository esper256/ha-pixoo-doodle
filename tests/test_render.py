from io import BytesIO

import pytest
from PIL import Image

from custom_components.pixoo_doodle.divoom_client.render import media, png, render


@pytest.mark.parametrize("size", [16, 64])
def test_render(size):
    base = Image.new("RGB", (size, size))
    for action in (
        "fill",
        "clear",
        "draw_pixels",
        "draw_line",
        "draw_rect",
        "draw_text",
        "scroll_text",
    ):
        frames = render(
            base,
            action,
            {
                "points": [(0, 0), (3, 3)],
                "font": "small",
                "text": "HELLO",
                "color": "#ff0000",
            },
        )
        assert 1 <= len(frames) <= 40
        assert all(im.size == base.size for im, _ in frames)
    assert base.getbbox() is None
    with pytest.raises(ValueError):
        render(base, "draw_pixels", {"points": [(size, 0)]})


def test_media():
    im = Image.new("RGB", (19, 9), "red")
    buf = BytesIO()
    im.save(
        buf,
        "GIF",
        save_all=True,
        append_images=[Image.new("RGB", im.size, "blue")],
        duration=[50, 100],
    )
    frames = media(buf.getvalue(), (16, 16), True, "crop", False)
    assert [d for _, d in frames] == [50, 100]
    image = media(png(im), (16, 16), False, "fit", True)[0][0]
    assert image.getpixel((0, 0)) == (0, 0, 0)


def test_bdf_and_gamma(tmp_path):
    bdf = tmp_path / "tiny.bdf"
    bdf.write_text("""STARTFONT 2.1
FONT tiny
SIZE 3 75 75
FONTBOUNDINGBOX 3 3 0 0
STARTPROPERTIES 0
ENDPROPERTIES
CHARS 1
STARTCHAR A
ENCODING 65
SWIDTH 1000 0
DWIDTH 3 0
BBX 3 3 0 0
BITMAP
40
A0
E0
ENDCHAR
ENDFONT
""")
    frame = render(
        Image.new("RGB", (16, 16)), "draw_text", {"text": "A", "font": str(bdf)}
    )[0][0]
    assert frame.getbbox() is not None
    src = png(Image.new("RGB", (16, 16), (128, 128, 128)))
    assert media(src, (16, 16), False, "fit", False, 2)[0][0].getpixel((0, 0)) == (
        64,
        64,
        64,
    )
