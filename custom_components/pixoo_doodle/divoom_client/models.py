"""Hardware profiles keyed by the manufacturer's numeric identifier."""

from dataclasses import dataclass

LEGACY = "/post"
MODERN = ":9000/divoom_api"


@dataclass(frozen=True, slots=True)
class Model:
    name: str
    resolution: tuple[int, int]
    endpoint: str
    family: str
    token_field: str | None = None

    @property
    def channels(self) -> bool:
        return self.family in ("pixoo16", "pixoo64")

    @property
    def supports_reboot(self) -> bool:
        return self.family in ("pixoo64", "gate", "frame")

    @property
    def buzzer_firmware(self) -> int | None:
        return 90109 if self.channels else None

    @property
    def native_text_firmware(self) -> int | None:
        return 90102 if self.family == "pixoo64" else None

    @property
    def gif_format(self) -> str | None:
        return {"pixoo16": "url_list", "pixoo64": "file_name", "gate": "lcd_list"}.get(
            self.family
        )

    @property
    def canvas(self) -> bool:
        return self.family in ("pixoo16", "pixoo64")

    @property
    def native_text(self) -> bool:
        return self.family == "pixoo64"

    @property
    def method(self) -> str:
        return "GET" if self.family == "frame" else "POST"


MODELS = {
    201: Model("Pixoo 16", (16, 16), LEGACY, "pixoo16"),
    **{
        i: Model("Pixoo 64", (64, 64), LEGACY, "pixoo64", "DeviceToken")
        for i in (90, 92)
    },
    96: Model("Pixoo 64", (64, 64), MODERN, "pixoo64"),
    400: Model("Times Gate", (128, 128), LEGACY, "gate", "LocalToken"),
    402: Model("Times Gate", (128, 128), MODERN, "gate"),
    **{i: Model("Times Frame", (800, 1280), MODERN, "frame") for i in (510, 511, 512)},
    530: Model("AstroToo", (480, 480), MODERN, "astro"),
}
