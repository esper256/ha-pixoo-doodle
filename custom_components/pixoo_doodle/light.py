from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry
from .entity import PixooEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([Display(entry.runtime_data, "display")])


class Display(PixooEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def brightness(self) -> int | None:
        value = self.coordinator.data.get("Brightness")
        return round(value * 255 / 100) if isinstance(value, int) else None

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        value = state.get("LightSwitch", state.get("OnOff"))
        return bool(value) if value is not None else None

    @property
    def assumed_state(self) -> bool:
        return (
            "LightSwitch" not in self.coordinator.data
            and self.coordinator.client.model.family != "astro"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.write("Channel/OnOffScreen", {"OnOff": 1}, {"OnOff": 1})
        if ATTR_BRIGHTNESS in kwargs:
            level = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            await self.coordinator.write(
                "Channel/SetBrightness", {"Brightness": level}, {"Brightness": level}
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write("Channel/OnOffScreen", {"OnOff": 0}, {"OnOff": 0})
