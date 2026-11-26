"""Share device configuration without identifying network or account details."""

from homeassistant.components.diagnostics import async_redact_data

from .coordinator import PixooConfigEntry

SAFE = {
    "Brightness",
    "SelectIndex",
    "LightSwitch",
    "OnOff",
    "RotationFlag",
    "ClockTime",
    "GalleryTime",
    "SingleGalleyTime",
    "PowerOnChannelId",
    "CurClockId",
    "Time24Flag",
    "TemperatureMode",
    "GyrateAngle",
    "MirrorFlag",
    "FirmwareVersion",
    "Hardware",
    "error_code",
    "ReturnCode",
    "CustomPageIndex",
}


def safe_state(data):
    return {
        key: value
        for key, value in data.items()
        if key in SAFE and isinstance(value, (int, bool, float, str))
    }


async def async_get_config_entry_diagnostics(hass, entry: PixooConfigEntry):
    runtime = entry.runtime_data
    return {
        "settings": async_redact_data(
            dict(entry.data), {"host", "mac", "device_id", "token"}
        ),
        "options": dict(entry.options),
        "model": runtime.client.model.name,
        "endpoint": runtime.client.endpoint,
        "configuration": safe_state(runtime.data),
    }
