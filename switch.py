"""The two things a person asserts: the cart is out, the bin is full."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STREAMS
from .entity import ReceptacleEntity, StreamEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(CartOutSwitch(coordinator, s) for s in STREAMS)

    for subentry_id, subentry in entry.subentries.items():
        async_add_entities(
            [HasWasteSwitch(coordinator, subentry_id, subentry.title)],
            config_subentry_id=subentry_id,
        )


class CartOutSwitch(StreamEntity, SwitchEntity):
    """Where the cart physically is. Not an instruction -- the binary_sensor
    carries whether it should move."""

    _attr_translation_key = "cart_out"

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "cart_out")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["streams"][self._stream]["cart_out"]

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_cart_out(self._stream, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_cart_out(self._stream, False)


class HasWasteSwitch(ReceptacleEntity, SwitchEntity):
    _attr_translation_key = "has_waste"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "has_waste")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["receptacles"].get(self._subentry_id, {}).get(
            "active", False
        )

    @property
    def extra_state_attributes(self) -> dict:
        row = self.coordinator.data["receptacles"].get(self._subentry_id, {})
        return {"stream": row.get("stream"), "since": row.get("since")}

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_has_waste(self._subentry_id, True)

    async def async_turn_off(self, **kwargs) -> None:
        # Turning it off is NOT the same as emptying it: the button stamps a
        # time, this only corrects the flag. Keeping them distinct is what
        # stops a mis-tap from writing a false emptied-at.
        await self.coordinator.async_set_has_waste(self._subentry_id, False)
