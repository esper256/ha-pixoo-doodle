"""Bounded, in-memory RGB rendering; coordinates refer to physical pixels."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import BdfFontFile, Image, ImageDraw, ImageFont, ImageOps

MAX_BYTES = 8 * 1024 * 1024
FONTS = {"small": 8, "large": 16}
type Frames = list[tuple[Image.Image, int]]


def png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def media(
    data: bytes,
    size: tuple[int, int],
    animated: bool,
    fit: str,
    dither: bool,
    gamma: float = 1.0,
) -> Frames:
    frames: Frames = []
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 4_000_000:
            raise ValueError("Image exceeds four megapixels")
        for i in range(40 if animated else 1):
            try:
                source.seek(i)
            except EOFError:
                break
            rgba = source.convert("RGBA")
            rgb = Image.new("RGB", rgba.size)
            rgb.paste(rgba, mask=rgba.getchannel("A"))
            image = (ImageOps.fit if fit == "crop" else ImageOps.pad)(
                rgb, size, method=Image.Resampling.LANCZOS
            )
            if gamma != 1.0:
                curve = [round(255 * (value / 255) ** gamma) for value in range(256)]
                image = image.point(curve * 3)
            if dither:
                image = image.convert(
                    "P", palette=Image.Palette.WEB, dither=Image.Dither.FLOYDSTEINBERG
                ).convert("RGB")
            frames.append(
                (image, max(10, min(60000, int(source.info.get("duration") or 100))))
            )
    return frames


def load_font(name: str) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    if name in FONTS:
        return ImageFont.truetype(
            str(Path(__file__).with_name("fonts") / "Silkscreen-Regular.ttf"),
            size=FONTS[name],
        )
    path = Path(name)
    if path.suffix.lower() != ".bdf" or path.stat().st_size > 1024 * 1024:
        raise ValueError("Expected a BDF pixel font under 1 MiB")
    with path.open("rb") as stream, TemporaryDirectory() as directory:
        try:
            font = BdfFontFile.BdfFontFile(stream)
        except (SyntaxError, KeyError, IndexError) as exc:
            raise ValueError("Invalid BDF font") from exc
        compiled = Path(directory) / "font.pil"
        font.save(str(compiled))
        return ImageFont.load(str(compiled))


def render(canvas: Image.Image, action: str, args: dict[str, Any]) -> Frames:
    image = canvas.copy()
    draw = ImageDraw.Draw(image)
    color = args.get("color", "#ffffff")
    if action in {"fill", "clear"}:
        image.paste(color if action == "fill" else "black", (0, 0, *image.size))
    elif action in {"draw_line", "draw_rect", "draw_pixels"}:
        points = args["points"]
        if any(not (0 <= x < image.width and 0 <= y < image.height) for x, y in points):
            raise ValueError("Pixel outside canvas")
        if action == "draw_pixels":
            draw.point(points, fill=color)
        elif action == "draw_line":
            draw.line(points, fill=color)
        else:
            draw.rectangle(
                points, outline=color, fill=color if args.get("filled") else None
            )
    else:
        font = load_font(args["font"])
        text = args["text"]
        width = round(draw.textlength(text, font=font))
        align = args.get("align", "left")
        start = {
            "left": 0,
            "center": (image.width - width) // 2,
            "right": image.width - width,
        }[align]
        positions = [start]
        if action == "scroll_text":
            distance = image.width + width
            count = min(40, distance + 1)
            positions = [
                image.width - round(i * distance / (count - 1)) for i in range(count)
            ]
        frames = []
        for x in positions:
            frame = image.copy()
            ImageDraw.Draw(frame).text(
                (x, args.get("y", 0)), text, font=font, fill=color, anchor="lt"
            )
            frames.append((frame, args.get("speed", 100)))
        return frames
    return [(image, 100)]
