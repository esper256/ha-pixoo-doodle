from homeassistant.components.select import SelectEntity
from .entity import CHANNELS, PixooEntity

PARALLEL_UPDATES = 1

CONTROLS = {
    "channel": (CHANNELS, "SelectIndex", "Channel/SetIndex", "SelectIndex"),
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


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.client.model.canvas:
        async_add_entities(Control(entry.runtime_data, key) for key in CONTROLS)


class Control(PixooEntity, SelectEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key)
        self._attr_options, self.field, self.command, self.param = CONTROLS[key]

    @property
    def current_option(self):
        index = self.coordinator.data.get(self.field)
        return (
            self.options[index]
            if isinstance(index, int) and 0 <= index < len(self.options)
            else None
        )

    async def async_select_option(self, option):
        index = self.options.index(option)
        await self.coordinator.write(
            self.command, {self.param: index}, {self.field: index}
        )
