"""Next pickup, last collected, last emptied, and the two roll-ups."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STREAMS
from .entity import ReceptacleEntity, StreamEntity, WasteEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for stream in STREAMS:
        entities.append(NextPickupSensor(coordinator, stream))
        entities.append(LastCollectedSensor(coordinator, stream))
    entities.append(ActiveReceptacleCountSensor(coordinator))
    entities.append(HouseholdNextPickupSensor(coordinator))
    async_add_entities(entities)

    # Receptacle entities are added AGAINST THEIR SUBENTRY, so Home Assistant
    # files each device under the subentry that created it and removing that
    # subentry takes its entities with it.
    for subentry_id, subentry in entry.subentries.items():
        async_add_entities(
            [LastEmptiedSensor(coordinator, subentry_id, subentry.title)],
            config_subentry_id=subentry_id,
        )


def _midday_local(day):
    """A pickup DATE rendered as a timestamp.

    Midday local, not midnight: `device_class: timestamp` renders an instant,
    and midnight is the value that lands on the wrong side of the day for any
    viewer an hour off. Nothing about the route claims a time -- the sensor's
    own attributes carry the date itself for anything that needs it exactly.
    """
    if day is None:
        return None
    return dt_util.start_of_local_day(day).replace(hour=12)


class NextPickupSensor(StreamEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_pickup"

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "next_pickup")

    @property
    def native_value(self):
        return _midday_local(self.coordinator.data["streams"][self._stream]["next_pickup"])

    @property
    def available(self) -> bool:
        # Unset schedule is a real, reportable state -- `unknown` with the gap
        # named in the attributes, never `unavailable`, which reads as broken.
        return True

    @property
    def extra_state_attributes(self) -> dict:
        row = self.coordinator.data["streams"][self._stream]
        return {
            **super().extra_state_attributes,
            "gap": row["gap"],
            "weekday": row["weekday"],
            "cadence": row["cadence"],
            # `days_until` predates `days_until_pickup` and is kept for the
            # board that reads it; they are one value under two names.
            "days_until": row["days_until"],
            "days_until_pickup": row["days_until"],
            "date": row["next_pickup"].isoformat() if row["next_pickup"] else None,
            "next_pickup_type": row["next_pickup_type"],
            "shifted_from": _shifted_from(row),
            "is_bin_out": row["cart_out"],
            "upcoming": [r["date"].isoformat() for r in row["upcoming"]],
            # The same four dates with their reason each, for a surface that
            # wants to mark the moved ones.
            "upcoming_detail": [
                {
                    "date": r["date"].isoformat(),
                    "type": r["type"],
                    "scheduled": r["scheduled"].isoformat(),
                }
                for r in row["upcoming"]
            ],
            "holidays": [d.isoformat() for d in self.coordinator.data["holidays"]],
            "overrides": {
                k: (v.isoformat() if v else None) for k, v in row["overrides"].items()
            },
        }


def _shifted_from(row) -> str | None:
    """The scheduled date, only when the next pickup is not on it."""
    if row["next_pickup"] is None or row["scheduled"] is None:
        return None
    if row["scheduled"] == row["next_pickup"]:
        return None
    return row["scheduled"].isoformat()


class HouseholdNextPickupSensor(WasteEntity, SensorEntity):
    """The soonest pickup of any stream, and which streams it is.

    One entity for the one question a wall tile asks -- what is next, when,
    and is its cart out -- so a surface does not have to read every stream
    sensor and pick the minimum itself.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "household_next_pickup"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "household_next_pickup", "household_next_pickup")

    @property
    def device_info(self):
        return _household_device(self.coordinator.entry_id)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return _midday_local(self.coordinator.data["household"]["next_pickup"])

    @property
    def extra_state_attributes(self) -> dict:
        row = self.coordinator.data["household"]
        return {
            "date": row["next_pickup"].isoformat() if row["next_pickup"] else None,
            "streams": row["streams"],
            "days_until_pickup": row["days_until"],
            "next_pickup_type": row["next_pickup_type"],
            "is_bin_out": row["is_bin_out"],
        }


def _household_device(entry_id: str):
    from homeassistant.helpers.device_registry import DeviceInfo

    from .entity import MANUFACTURER

    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Waste Collection",
        manufacturer=MANUFACTURER,
        model="Household waste",
    )


class LastCollectedSensor(StreamEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_collected"

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "last_collected")

    @property
    def native_value(self):
        return self.coordinator.as_datetime(
            self.coordinator.data["streams"][self._stream]["collected"]
        )


class LastEmptiedSensor(ReceptacleEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_emptied"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "last_emptied")

    @property
    def native_value(self):
        row = self.coordinator.data["receptacles"].get(self._subentry_id, {})
        return self.coordinator.as_datetime(row.get("emptied"))


class ActiveReceptacleCountSensor(WasteEntity, SensorEntity):
    """How many bins are holding waste, longest-waiting named first."""

    _attr_translation_key = "active_receptacles"
    _attr_native_unit_of_measurement = "receptacles"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "active_receptacles", "active_receptacles")

    @property
    def device_info(self):
        return _household_device(self.coordinator.entry_id)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.active_receptacles)

    @property
    def extra_state_attributes(self) -> dict:
        rows = self.coordinator.active_receptacles
        return {
            "receptacles": [r["name"] for r in rows],
            "oldest": rows[0]["name"] if rows else None,
            "oldest_since": rows[0].get("since") if rows else None,
        }
