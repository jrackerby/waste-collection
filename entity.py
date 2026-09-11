"""DeviceInfo, defined once -- the household_state / kiosk_pi convention.

TWO KINDS OF DEVICE, and the split is the whole point of this integration.

A STREAM device is the route: trash or recycling, its schedule, its curb
cart. There is one per entry per stream and it is not tied to any room.

A RECEPTACLE device is a bin in a room, created from a config subentry. It
gets its own device row precisely so it can be dropped into a Home Assistant
AREA in the UI. The YAML-helper design this replaces had to encode the room
in the entity id (`waste_point_<room>_<stream>`) and parse it back out,
because a helper cannot carry an area. Nothing here parses an id.
"""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

MANUFACTURER = "El Coronel Luz"


class WasteEntity(CoordinatorEntity):
    """Base for everything this integration publishes.

    `_attr_has_entity_name = True` so ids slug from the device name --
    sensor.trash_collection_next_pickup, not
    sensor.trash_collection_next_pickup_next_pickup.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, key: str, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry_id}_{unique_suffix}"


class StreamEntity(WasteEntity):
    """An entity belonging to one collection stream."""

    def __init__(self, coordinator, stream: str, key: str) -> None:
        super().__init__(coordinator, key, f"{stream}_{key}")
        self._stream = stream

    @property
    def extra_state_attributes(self) -> dict:
        """Which stream this entity belongs to, on EVERY stream entity.

        A consumer must never have to work this out for itself. The two
        things it could otherwise read are both wrong: a device name is
        renameable, and an entity id is frozen at creation and must never be
        parsed for meaning. The receptacle switch has always
        carried `stream`; this is the same contract on the other side of the
        integration. Subclasses with attributes of their own merge over it.
        """
        return {"stream": self._stream}

    @property
    def device_info(self) -> DeviceInfo:
        label = self._stream.replace("_", " ").title()
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.entry_id}_{self._stream}")},
            name=f"{label} Collection",
            manufacturer=MANUFACTURER,
            model="Collection route",
        )


class ReceptacleEntity(WasteEntity):
    """An entity belonging to one receptacle, created from a subentry.

    Identifiers key on the SUBENTRY id, never on the name: renaming a bin in
    the UI must not orphan its device and mint a second one alongside it.
    """

    def __init__(self, coordinator, subentry_id: str, name: str, key: str) -> None:
        super().__init__(coordinator, key, f"{subentry_id}_{key}")
        self._subentry_id = subentry_id
        self._receptacle_name = name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"receptacle_{self._subentry_id}")},
            name=self._receptacle_name,
            manufacturer=MANUFACTURER,
            model="Receptacle",
        )
