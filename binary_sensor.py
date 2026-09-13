"""Is the cart due out."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CART_DUE, DOMAIN, STREAMS
from .entity import StreamEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(SetoutDueBinarySensor(coordinator, s) for s in STREAMS)


class SetoutDueBinarySensor(StreamEntity, BinarySensorEntity):
    _attr_translation_key = "setout_due"

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "setout_due")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["streams"][self._stream]["status"] == CART_DUE

    @property
    def extra_state_attributes(self) -> dict:
        row = self.coordinator.data["streams"][self._stream]
        # `status` carries the case is_on cannot: a cart still at the curb the
        # day after its pickup needs bringing IN, which is neither due nor idle.
        return {
            **super().extra_state_attributes,
            "status": row["status"],
            "days_until": row["days_until"],
            "days_until_pickup": row["days_until"],
            "next_pickup_type": row["next_pickup_type"],
            "is_bin_out": row["cart_out"],
        }
