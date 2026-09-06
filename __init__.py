"""Waste Collection -- receptacles, curb carts and the collection calendar."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WasteCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = WasteCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding or removing a receptacle is a subentry change, and a subentry
    # change does not reload the entry on its own -- without this a bin added
    # in the UI appears only after a restart, which is exactly the friction
    # this integration exists to remove.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_remove_config_entry_device(hass: HomeAssistant, entry, device) -> bool:
    """Let a stale receptacle device be deleted from the UI.

    Returning True unconditionally is wrong for a device the entry still
    owns, so this checks: a device whose identifier still matches a live
    subentry or stream stays.
    """
    live = {f"{entry.entry_id}_{s}" for s in ("trash", "recycling")}
    live |= {f"receptacle_{sid}" for sid in entry.subentries}
    return not any(ident[1] in live for ident in device.identifiers if ident[0] == DOMAIN)
