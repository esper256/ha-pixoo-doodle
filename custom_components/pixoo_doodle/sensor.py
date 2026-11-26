from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry, RuntimeData
from .entity import CHANNELS, PixooEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    keys = ["hardware", "firmware", "resolution", "endpoint"]
    if entry.runtime_data.client.model.channels:
        keys.append("current_channel")
    async_add_entities(Diagnostic(entry.runtime_data, key) for key in keys)


class Diagnostic(PixooEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: RuntimeData, key: str) -> None:
        super().__init__(runtime, key)
        self.key = key
        self._attr_entity_registry_enabled_default = key != "endpoint"

    @property
    def native_value(self) -> int | str | None:
        c = self.coordinator.client
        match self.key:
            case "hardware":
                return c.hardware
            case "firmware":
                return self.coordinator.data.get("FirmwareVersion")
            case "resolution":
                return "×".join(map(str, c.model.resolution))
            case "endpoint":
                return c.endpoint
            case "current_channel":
                i = self.coordinator.data.get("SelectIndex")
                return (
                    CHANNELS[i]
                    if isinstance(i, int) and 0 <= i < len(CHANNELS)
                    else None
                )
        return None
