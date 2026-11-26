from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry, RuntimeData
from .entity import PixooEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controls = [
        Setting(entry.runtime_data, "hour24", "Time24Flag", "Device/SetTime24Flag")
    ]
    if entry.runtime_data.client.model.family != "astro":
        controls.append(
            Setting(entry.runtime_data, "mirror", "MirrorFlag", "Device/SetMirrorMode")
        )
    async_add_entities(controls)


class Setting(PixooEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, runtime: RuntimeData, key: str, field: str, command: str
    ) -> None:
        super().__init__(runtime, key)
        self.field, self.command = field, command

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get(self.field)
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.write(self.command, {"Mode": 1}, {self.field: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write(self.command, {"Mode": 0}, {self.field: 0})
