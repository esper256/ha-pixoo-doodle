from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry, RuntimeData
from .divoom_client import Json
from .entity import PixooEntity

PARALLEL_UPDATES = 1
BUZZ = {"ActiveTimeInCycle": 100, "OffTimeInCycle": 100, "PlayTotalTime": 100}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    buttons = []
    if runtime.client.model.supports_reboot:
        buttons.append(Action(runtime, "reboot", "Device/SysReboot", {}))
    if (
        minimum := runtime.client.model.buzzer_firmware
    ) is not None and runtime.firmware_allows(minimum):
        buttons.append(Action(runtime, "buzzer", "Device/PlayBuzzer", BUZZ))
    async_add_entities(buttons)


class Action(PixooEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, runtime: RuntimeData, key: str, command: str, fields: Json
    ) -> None:
        super().__init__(runtime, key)
        self.command, self.fields = command, fields

    async def async_press(self) -> None:
        await self.coordinator.write(self.command, self.fields)
