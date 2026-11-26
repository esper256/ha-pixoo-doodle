from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry, RuntimeData
from .entity import CHANNELS, PixooEntity

PARALLEL_UPDATES = 1

CONTROLS = {
    "channel": (CHANNELS, "SelectIndex", "Channel/SetIndex", "SelectIndex"),
    "visualizer": (
        [str(i) for i in range(8)],
        "EqPosition",
        "Channel/SetEqPosition",
        "EqPosition",
    ),
    "custom_page": (
        ["0", "1", "2"],
        "CustomPageIndex",
        "Channel/SetCustomPageIndex",
        "CustomPageIndex",
    ),
    "rotation": (
        ["0", "90", "180", "270"],
        "RotationFlag",
        "Device/SetScreenRotationAngle",
        "Mode",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if entry.runtime_data.client.model.channels:
        async_add_entities(
            [
                *(Control(entry.runtime_data, key) for key in CONTROLS),
                Face(entry.runtime_data, "clock_face"),
            ]
        )


class Control(PixooEntity, SelectEntity):
    def __init__(self, runtime: RuntimeData, key: str) -> None:
        super().__init__(runtime, key)
        self._attr_options, self.field, self.command, self.param = CONTROLS[key]

    @property
    def current_option(self) -> str | None:
        index = self.coordinator.data.get(self.field)
        return (
            self.options[index]
            if isinstance(index, int) and 0 <= index < len(self.options)
            else None
        )

    async def async_select_option(self, option: str) -> None:
        index = self.options.index(option)
        await self.coordinator.write(
            self.command, {self.param: index}, {self.field: index}
        )


class Face(PixooEntity, SelectEntity):
    @property
    def current_option(self) -> str | None:
        face = self.coordinator.data.get("CurClockId")
        return str(face) if face is not None else None

    @property
    def options(self) -> list[str]:
        choices = {str(face) for face in self.coordinator.faces}
        if self.current_option is not None:
            choices.add(self.current_option)
        return sorted(choices, key=int)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.write(
            "Channel/SetClockSelectId", {"ClockId": int(option)}
        )
