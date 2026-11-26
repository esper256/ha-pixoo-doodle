"""Opt-in vendor cloud lookups."""

from aiohttp import ClientSession
from . import DeviceError, Json, request

BASE = "https://app.divoom-gz.com"


async def discover(session: ClientSession) -> list[Json]:
    result = await request(session, "POST", BASE + "/Device/ReturnSameLANDevice", {})
    rows = result.get("DeviceList")
    if not isinstance(rows, list):
        raise DeviceError("Invalid discovery list")
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("DevicePrivateIP")
        and (row.get("DeviceMac") or row.get("DeviceId"))
    ]


async def catalog(
    session: ClientSession, kind: str, dial_type: str = "", page: int = 1
) -> Json:
    routes = {
        "fonts": "/Device/GetTimeDialFontList",
        "faces": "/Channel/GetDialList",
        "types": "/Channel/GetDialType",
    }
    fields = {"DialType": dial_type, "Page": page} if kind == "faces" else {}
    return await request(session, "POST", BASE + routes[kind], fields)
