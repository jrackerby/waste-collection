"""The one accessor every platform reads, and the only writer of stored state.

WHY A COORDINATOR AT ALL when nothing here does I/O. Two reasons, and neither
is polling a device:

  1. Every derived answer depends on TODAY. `next_pickup` and `setout_due`
     change at midnight with no state change to trigger them, so something has
     to re-evaluate on a timer or a display spends collection morning saying
     the truck comes in seven days.
  2. One reduction, read by four platforms. A value read by two code paths goes
     through one accessor: when a cart card and a schedule card each read the
     stored values themselves, a stream could be "unscheduled" on one and show
     four upcoming dates on the other.

STORED STATE IS SEPARATE FROM DERIVED STATE. Cart-out, has-waste and the two
timestamps are asserted by a person and must survive a restart, so they live
in a `Store`. Everything else is computed from them plus the clock and is
never persisted -- a stored derived value is a value that can be stale and
right-looking at the same time.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ANCHOR,
    CONF_CADENCE,
    CONF_NAME,
    CONF_STREAM,
    CONF_WEEKDAY,
    DOMAIN,
    STREAMS,
    UPCOMING_COUNT,
    WEEKDAYS,
)
from .resolver import (
    cart_status,
    days_until,
    next_pickups,
    parse_anchor,
    schedule_gap,
    weekday_index,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Recompute often enough that a midnight rollover shows up promptly without
# scheduling against the clock directly. The work is pure arithmetic over a
# handful of dates; the cost of the interval is not the reason to widen it.
UPDATE_INTERVAL = timedelta(minutes=5)


class WasteCoordinator(DataUpdateCoordinator):
    """Reduces stored state plus the calendar into what every platform renders."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.entry_id = entry.entry_id
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._state: dict[str, Any] = {}

    # -- stored state ------------------------------------------------------

    async def async_load(self) -> None:
        self._state = await self._store.async_load() or {}

    async def _async_persist(self) -> None:
        await self._store.async_save(self._state)
        # Immediate, not debounced. The coordinator debouncer's cooldown is
        # 10s, so a SECOND assertion inside it waits out the remainder --
        # measured against live core at 0.02s for an isolated tap and 10.18s
        # for a back-to-back one. The surface these entities feed is a wall
        # panel where somebody walks the house tapping bins in a row, so
        # every tap after the first read as ignored and invited a second
        # press on a control that had already fired. A debouncer coalesces
        # polls of a remote device; there is no device here, and the update
        # is pure arithmetic over a handful of dates.
        await self.async_refresh()

    def _get(self, scope: str, key: str, default=None):
        return self._state.get(scope, {}).get(key, default)

    async def _async_set(self, scope: str, key: str, value) -> None:
        self._state.setdefault(scope, {})[key] = value
        await self._async_persist()

    # -- the writes the platforms make -------------------------------------

    async def async_set_cart_out(self, stream: str, out: bool) -> None:
        await self._async_set(f"stream_{stream}", "cart_out", out)

    async def async_mark_collected(self, stream: str) -> None:
        """The truck came: stamp it AND bring the cart in.

        One event in the world, so one action. Splitting them into two taps is
        how a surface ends up permanently claiming a cart is at the curb.
        """
        scope = f"stream_{stream}"
        self._state.setdefault(scope, {})
        self._state[scope]["collected"] = dt_util.utcnow().isoformat()
        self._state[scope]["cart_out"] = False
        await self._async_persist()

    async def async_set_has_waste(self, subentry_id: str, active: bool) -> None:
        scope = f"receptacle_{subentry_id}"
        self._state.setdefault(scope, {})
        self._state[scope]["active"] = active
        if active:
            self._state[scope]["since"] = dt_util.utcnow().isoformat()
        await self._async_persist()

    async def async_mark_emptied(self, subentry_id: str) -> None:
        scope = f"receptacle_{subentry_id}"
        self._state.setdefault(scope, {})
        self._state[scope]["active"] = False
        self._state[scope]["emptied"] = dt_util.utcnow().isoformat()
        await self._async_persist()

    # -- the reduction -----------------------------------------------------

    def _schedule(self, stream: str) -> dict[str, Any]:
        return (self.entry.options.get(stream) or {}) if self.entry.options else {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Never raises. There is no subject that can be unreachable here --
        the inputs are this entry's own options and the clock -- so an
        exception would only ever be a bug in the arithmetic, and taking every
        entity unavailable is the worst way to report one."""
        today: date = dt_util.now().date()
        return {
            "today": today,
            "streams": {s: self._reduce_stream(s, today) for s in STREAMS},
            "receptacles": self._reduce_receptacles(),
        }

    def _reduce_stream(self, stream: str, today: date) -> dict[str, Any]:
        cfg = self._schedule(stream)
        weekday = weekday_index(cfg.get(CONF_WEEKDAY), WEEKDAYS)
        cadence = cfg.get(CONF_CADENCE)
        anchor = parse_anchor(cfg.get(CONF_ANCHOR))

        gap = schedule_gap(weekday, cadence, anchor)
        upcoming = next_pickups(weekday, cadence, anchor, today, UPCOMING_COUNT)
        nxt = upcoming[0] if upcoming else None
        cart_out = bool(self._get(f"stream_{stream}", "cart_out", False))

        return {
            "gap": gap,
            "weekday": cfg.get(CONF_WEEKDAY),
            "cadence": cadence,
            "anchor": anchor,
            "next_pickup": nxt,
            "upcoming": upcoming,
            "days_until": days_until(nxt, today) if nxt else None,
            "cart_out": cart_out,
            "status": cart_status(nxt, cart_out, today),
            "collected": self._get(f"stream_{stream}", "collected"),
        }

    def _reduce_receptacles(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for subentry in self.entry.subentries.values():
            scope = f"receptacle_{subentry.subentry_id}"
            out[subentry.subentry_id] = {
                "name": subentry.data.get(CONF_NAME, subentry.title),
                "stream": subentry.data.get(CONF_STREAM),
                "active": bool(self._get(scope, "active", False)),
                "since": self._get(scope, "since"),
                "emptied": self._get(scope, "emptied"),
            }
        return out

    # -- convenience for the roll-up sensors -------------------------------

    @property
    def active_receptacles(self) -> list[dict[str, Any]]:
        """Longest-waiting first: this is an action list, not an inventory."""
        rows = [r for r in (self.data or {}).get("receptacles", {}).values() if r["active"]]
        return sorted(rows, key=lambda r: r.get("since") or "")

    @staticmethod
    def as_datetime(value) -> datetime | None:
        return dt_util.parse_datetime(value) if value else None
