from homeassistant.components.number import NumberEntity
from homeassistant.const import EntityCategory

from .entity import PixooEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Brightness(entry.runtime_data, "brightness")])


class Brightness(PixooEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        return self.coordinator.data.get("Brightness")

    async def async_set_native_value(self, value):
        await self.coordinator.write(
            "Channel/SetBrightness",
            {"Brightness": int(value)},
            {"Brightness": int(value)},
        )
