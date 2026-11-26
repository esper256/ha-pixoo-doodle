"""Common device identity and entity naming."""

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DOMAIN, RuntimeData

CHANNELS = ["faces", "cloud", "visualizer", "custom", "black_screen"]


class PixooEntity(CoordinatorEntity[RuntimeData]):
    _attr_has_entity_name = True

    def __init__(self, runtime: RuntimeData, key: str):
        super().__init__(runtime)
        entry = runtime.entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            connections={(CONNECTION_NETWORK_MAC, entry.data["mac"])}
            if "mac" in entry.data
            else set(),
            name=entry.title,
            manufacturer="Divoom",
            model=runtime.client.model.name,
            hw_version=str(runtime.client.hardware),
            sw_version=str(runtime.data["FirmwareVersion"])
            if runtime.data.get("FirmwareVersion")
            else None,
        )
