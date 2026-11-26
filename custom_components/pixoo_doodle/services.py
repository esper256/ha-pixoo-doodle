"""Device-targeted actions and persistent per-entry drawing."""

from base64 import b64encode
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import probatio as vol
from aiohttp import ClientError, ClientTimeout
from homeassistant.components import media_source
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from PIL import Image

from .button import BUZZ
from .coordinator import DOMAIN, RuntimeData
from .divoom_client import DeviceError, Json
from .divoom_client.cloud import catalog
from .divoom_client.render import FONTS, MAX_BYTES, media, png, render


def integer(low: int, high: int) -> vol.All[int]:
    return vol.All(vol.Coerce(int), vol.Range(min=low, max=high))


COLOR = {vol.Optional("color", default="#ffffff"): vol.Match(r"^#[a-fA-F0-9]{6}$")}
COMMIT = {vol.Optional("commit", default=True): cv.boolean}
POINT = vol.ExactSequence((integer(0, 127), integer(0, 127)))
TEXT: dict[Any, Any] = {
    vol.Required("text"): vol.All(str, vol.Length(min=1, max=160)),
    vol.Optional("font"): str,
    vol.Optional("align", default="left"): vol.In(["left", "center", "right"]),
    vol.Optional("y", default=0): integer(0, 63),
    **COLOR,
}
MEDIA = {
    vol.Required("source"): str,
    vol.Optional("fit", default="fit"): vol.In(["fit", "crop"]),
    vol.Optional("dither", default=False): cv.boolean,
    vol.Optional("gamma", default=1.0): vol.All(
        vol.Coerce(float), vol.Range(min=0.1, max=4)
    ),
}
SHAPES: dict[Any, Any] = {
    vol.Required("points"): vol.All([POINT], vol.Length(min=2, max=2)),
    **COLOR,
    **COMMIT,
}
FIELDS: dict[Any, Any] = {
    "draw_text": TEXT,
    "scroll_text": {**TEXT, vol.Optional("speed", default=100): integer(10, 1000)},
    "show_image": MEDIA,
    "play_gif": MEDIA,
    "draw_pixels": {
        vol.Required("points"): vol.All([POINT], vol.Length(min=1, max=4096)),
        **COLOR,
        **COMMIT,
    },
    "draw_line": SHAPES,
    "draw_rect": {**SHAPES, vol.Optional("filled", default=False): cv.boolean},
    "fill": {**COLOR, **COMMIT},
    "clear": COMMIT,
    "set_timer": {
        vol.Required("minute"): integer(0, 59),
        vol.Optional("second", default=0): integer(0, 59),
        vol.Optional("status", default=1): integer(0, 1),
    },
    "stopwatch": {vol.Required("status"): integer(0, 2)},
    "scoreboard": {
        vol.Required("blue"): integer(0, 999),
        vol.Required("red"): integer(0, 999),
    },
    "play_buzzer": {},
    "select_clock_face": {vol.Required("clock_id"): integer(0, 2147483647)},
    "refresh": {},
    "get_canvas": {},
    "get_fonts": {},
    "get_faces": {
        vol.Required("dial_type"): str,
        vol.Optional("page", default=1): integer(1, 10000),
    },
    "get_config": {},
}
DRAW = {
    "draw_text",
    "scroll_text",
    "show_image",
    "play_gif",
    "draw_pixels",
    "draw_line",
    "draw_rect",
    "fill",
    "clear",
}


def invalid(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


async def load_media(hass: HomeAssistant, source: str) -> bytes:
    def read(path: str | Path, roots: Iterable[str] | None = None) -> bytes:
        path = Path(path).resolve(strict=True)
        allowed = (
            any(path.is_relative_to(Path(root).resolve()) for root in roots)
            if roots is not None
            else hass.config.is_allowed_path(str(path))
        )
        if not allowed or not path.is_file():
            raise invalid("invalid_media")
        with path.open("rb") as stream:
            return stream.read(MAX_BYTES + 1)

    if media_source.is_media_source_id(source):
        resolved = await media_source.async_resolve_media(hass, source, None)
        if resolved.path:
            data = await hass.async_add_executor_job(
                read, resolved.path, hass.config.media_dirs.values()
            )
            if len(data) > MAX_BYTES:
                raise invalid("invalid_media")
            return data
        source = resolved.url
    if source.startswith(("https://", "http://")):
        async with async_get_clientsession(hass).get(
            source, timeout=ClientTimeout(total=15), allow_redirects=False
        ) as response:
            if response.status != 200:
                raise invalid("invalid_media")
            buffer = bytearray()
            async for part in response.content.iter_chunked(65536):
                buffer.extend(part)
                if len(buffer) > MAX_BYTES:
                    raise invalid("invalid_media")
            return bytes(buffer)
    if not Path(source).is_absolute():
        raise invalid("invalid_media")
    data = await hass.async_add_executor_job(read, source)
    if len(data) > MAX_BYTES:
        raise invalid("invalid_media")
    return data


async def draw(runtime: RuntimeData, action: str, args: Json) -> None:
    if runtime.canvas is None:
        raise invalid("unsupported")
    async with runtime.canvas_lock:
        hass = runtime.hass
        if action in ("show_image", "play_gif"):
            data = await load_media(hass, args["source"])
            frames = await hass.async_add_executor_job(
                media,
                data,
                runtime.canvas.size,
                action == "play_gif",
                args["fit"],
                args["dither"],
                args.get("gamma", 1.0),
            )
        else:
            args.setdefault("font", runtime.entry.options.get("default_font", "small"))
            if action in ("draw_text", "scroll_text") and args["font"] not in FONTS:

                def allowed_font() -> str:
                    path = Path(args["font"]).resolve(strict=True)
                    if (
                        not hass.config.is_allowed_path(str(path))
                        or path.suffix.lower() != ".bdf"
                    ):
                        raise invalid("invalid_drawing")
                    return str(path)

                args["font"] = await hass.async_add_executor_job(allowed_font)
            frames = await hass.async_add_executor_job(
                render, runtime.canvas, action, args
            )
        image = frames[0][0]
        if args.get("commit", True):
            native = (
                action in ("draw_text", "scroll_text")
                and args["font"] in FONTS
                and runtime.client.model.native_text
                and len(args["text"].encode()) < 512
                and runtime.firmware_allows(
                    runtime.client.model.native_text_firmware or 0
                )
            )
            send = [(runtime.canvas, 100)] if native else frames
            await runtime.client.push([(im.tobytes(), delay) for im, delay in send])
            if native:
                await runtime.client.command(
                    "Draw/SendHttpText",
                    TextId=0,
                    x=0,
                    y=args["y"],
                    dir=0,
                    font=0 if args["font"] == "small" else 1,
                    TextWidth=image.width,
                    TextString=args["text"],
                    speed=args.get("speed", 100),
                    color=args["color"],
                    align=["left", "center", "right"].index(args["align"]) + 1,
                )
            runtime.preview = await hass.async_add_executor_job(png, image)
            runtime.preview_time = datetime.now(UTC)
            runtime.async_update_listeners()
        runtime.canvas = image


async def dispatch(r: RuntimeData, action: str, args: dict[str, Any]) -> Json:
    family = r.client.model.family
    if action in DRAW:
        await draw(r, action, args)
    elif action == "get_canvas":
        if not r.preview:
            raise invalid("no_preview")
        return {"png": b64encode(r.preview).decode()}
    elif action == "get_config":
        from .diagnostics import safe_state

        return safe_state(await r.client.state())
    elif action in ("get_fonts", "get_faces"):
        if not r.client.model.canvas:
            raise invalid("unsupported")
        from homeassistant.helpers import issue_registry as ir

        try:
            result = await catalog(
                r.client.session,
                "faces" if action == "get_faces" else "fonts",
                args.get("dial_type", ""),
                args.get("page", 1),
            )
        except DeviceError:
            r.issue("cloud_unreachable")
            raise
        ir.async_delete_issue(r.hass, DOMAIN, f"{r.entry.entry_id}_cloud_unreachable")
        if action == "get_faces":
            r.faces.update(
                row["ClockId"]
                for row in result.get("DialList", [])
                if isinstance(row, dict) and type(row.get("ClockId")) is int
            )
            r.async_update_listeners()
        return result
    elif action == "refresh":
        await r.async_refresh()
        if not r.last_update_success:
            raise DeviceError
    elif action == "play_buzzer":
        if (minimum := r.client.model.buzzer_firmware) is None:
            raise invalid("unsupported")
        if not r.firmware_allows(minimum):
            r.issue("old_firmware")
            raise invalid("unsupported")
        await r.write("Device/PlayBuzzer", BUZZ)
    elif action == "select_clock_face":
        if family == "astro":
            raise invalid("unsupported")
        await r.write(
            "Channel/Set5LcdWholeClockId"
            if family == "gate"
            else "Channel/SetClockSelectId",
            {"ClockId": args["clock_id"]},
        )
    elif action == "set_timer":
        await r.write(
            "Tools/SetTimer",
            {
                "Minute": args["minute"],
                "Second": args["second"],
                "Status": args["status"],
            },
        )
    elif action == "stopwatch":
        await r.write("Tools/SetStopWatch", {"Status": args["status"]})
    elif action == "scoreboard":
        await r.write(
            "Tools/SetScoreBoard", {"RedScore": args["red"], "BlueScore": args["blue"]}
        )
    return {}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def handle(call: ServiceCall) -> Json | None:
        args = dict(call.data)
        entry_id = args.pop("config_entry_id", None)
        device_ids = args.pop("device_id", [])
        if isinstance(device_ids, str):
            device_ids = [device_ids]
        if bool(entry_id) == bool(device_ids):
            raise invalid("invalid_target")
        ids = {entry_id} if entry_id else set()
        for device_id in device_ids:
            device = dr.async_get(hass).async_get(device_id)
            if not device or not device.config_entry_id:
                raise invalid("invalid_target")
            ids.add(device.config_entry_id)
        result = {}
        entries = [hass.config_entries.async_get_entry(i) for i in ids]
        if not entries or any(
            e is None or e.domain != DOMAIN or e.state != ConfigEntryState.LOADED
            for e in entries
        ):
            raise invalid("invalid_target")
        for entry in entries:
            assert entry is not None
            try:
                result[entry.entry_id] = await dispatch(
                    entry.runtime_data, call.service, args.copy()
                )
                if (
                    call.return_response
                    and call.service in DRAW
                    and entry.runtime_data.preview
                ):
                    result[entry.entry_id] = {
                        "png": b64encode(entry.runtime_data.preview).decode()
                    }
            except (DeviceError, TimeoutError, ClientError) as exc:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="device_error"
                ) from exc
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise invalid("invalid_drawing") from exc
        return result if call.return_response else None

    for name, fields in FIELDS.items():
        response = (
            SupportsResponse.ONLY
            if name.startswith("get_")
            else SupportsResponse.OPTIONAL
            if name in DRAW
            else SupportsResponse.NONE
        )
        hass.services.async_register(
            DOMAIN,
            name,
            handle,
            vol.Schema(
                {
                    vol.Optional("device_id"): vol.Any(str, [str]),
                    vol.Optional("config_entry_id"): str,
                    **fields,
                }
            ),
            supports_response=response,
        )
