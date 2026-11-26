from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixooConfigEntry, RuntimeData
from .entity import PixooEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PixooConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if entry.runtime_data.client.model.canvas:
        async_add_entities([Preview(entry.runtime_data)])


class Preview(PixooEntity, ImageEntity):
    _attr_content_type = "image/png"

    def __init__(self, runtime: RuntimeData) -> None:
        ImageEntity.__init__(self, runtime.hass)
        PixooEntity.__init__(self, runtime, "preview")

    @property
    def image_last_updated(self) -> datetime | None:
        return self.coordinator.preview_time

    async def async_image(self) -> bytes | None:
        return self.coordinator.preview
