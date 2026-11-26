from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .entity import PixooEntity

PARALLEL_UPDATES = 1
BUZZ = {"ActiveTimeInCycle": 100, "OffTimeInCycle": 100, "PlayTotalTime": 100}


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    buttons = []
    if runtime.client.model.family in ("pixoo64", "frame", "gate"):
        buttons.append(Action(runtime, "reboot", "Device/SysReboot", {}))
    if (
        runtime.client.model.canvas
        and int(runtime.data.get("FirmwareVersion", 90109)) >= 90109
    ):
        buttons.append(Action(runtime, "buzzer", "Device/PlayBuzzer", BUZZ))
    async_add_entities(buttons)


class Action(PixooEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, runtime, key, command, fields):
        super().__init__(runtime, key)
        self.command, self.fields = command, fields

    async def async_press(self):
        await self.coordinator.write(self.command, self.fields)
