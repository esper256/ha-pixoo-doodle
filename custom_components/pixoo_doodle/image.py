from homeassistant.components.image import ImageEntity
from .entity import PixooEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.client.model.canvas:
        async_add_entities([Preview(entry.runtime_data)])


class Preview(PixooEntity, ImageEntity):
    _attr_content_type = "image/png"

    def __init__(self, runtime):
        ImageEntity.__init__(self, runtime.hass)
        PixooEntity.__init__(self, runtime, "preview")

    @property
    def image_last_updated(self):
        return self.coordinator.preview_time

    async def async_image(self):
        return self.coordinator.preview
