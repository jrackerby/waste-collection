"""Two events worth stamping: the truck came, and the bin went out."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STREAMS
from .entity import ReceptacleEntity, StreamEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(CollectedButton(coordinator, s) for s in STREAMS)

    for subentry_id, subentry in entry.subentries.items():
        async_add_entities(
            [EmptiedButton(coordinator, subentry_id, subentry.title)],
            config_subentry_id=subentry_id,
        )


class CollectedButton(StreamEntity, ButtonEntity):
    _attr_translation_key = "collected"

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "collected")

    async def async_press(self) -> None:
        await self.coordinator.async_mark_collected(self._stream)


class EmptiedButton(ReceptacleEntity, ButtonEntity):
    _attr_translation_key = "emptied"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "emptied")

    async def async_press(self) -> None:
        await self.coordinator.async_mark_emptied(self._subentry_id)
