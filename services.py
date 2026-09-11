"""The `set_schedule` action -- the only write that is not an entity.

WHY A SERVICE EXISTS FOR THIS AT ALL. The pickup day, the cadence and the
every-other-week anchor are config-entry OPTIONS, and options are reachable
only through an options flow -- a form, in Settings. A dashboard has
`callService` and nothing else, so without this action the schedule is
reachable from Settings and from nowhere else -- not from a dashboard button,
not from a script, not from an automation. A display exists so nobody has to
open Home Assistant; a setting only Settings can reach moves the wrong way.

WHAT IT REFUSES, AND WHY THAT IS THE FEATURE. `validate_changes()` raises on a
weekday or cadence it does not recognise instead of dropping or defaulting it.
Home Assistant answers a service call 200 even on a silent no-op, so a
dashboard button cannot tell a stored schedule from an ignored one. Every refusal here is
raised as `ServiceValidationError`, which is the one class HA reports back to
the caller as a real error rather than logging a traceback and answering
success.

A call naming no field at all is refused for the same reason. `stream` alone
is well-formed, changes nothing, and would answer 200 -- indistinguishable
from a schedule that was set.

EVERY VALUE CHECK LIVES IN `schedule_options`, none of them in the voluptuous
schema below. That is deliberate and it is not a style preference: the test
suite runs with Home Assistant absent (tests/conftest.py), so a `vol.In(...)`
here would move the guarantee this action exists to give into a schema no test
in this repo can reach. The schema is left to do only what the pure module
cannot -- require `stream`, and reject a call that names no field.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_ANCHOR, CONF_CADENCE, CONF_STREAM, CONF_WEEKDAY, DOMAIN
from .schedule_options import (
    ScheduleValueError,
    merge_stream_options,
    validate_changes,
    validate_stream,
)

SERVICE_SET_SCHEDULE = "set_schedule"

# Shape only -- see the module docstring. `has_at_least_one_key` is what stops
# the well-formed no-op; selectors are declared in services.yaml, so the UI
# still offers dropdowns rather than free text.
SET_SCHEDULE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(CONF_STREAM): cv.string,
            vol.Optional(CONF_WEEKDAY): vol.Any(None, cv.string),
            vol.Optional(CONF_CADENCE): vol.Any(None, cv.string),
            vol.Optional(CONF_ANCHOR): vol.Any(None, cv.string),
        }
    ),
    cv.has_at_least_one_key(CONF_WEEKDAY, CONF_CADENCE, CONF_ANCHOR),
)


def _entry(hass: HomeAssistant) -> ConfigEntry:
    """The one config entry, or a caller-visible error.

    `single_config_entry` in the manifest makes "the one" well defined, so
    this takes no target and the board's call carries no entry id it would
    have to learn. A missing entry is a real answer to give: this action is
    registered in `async_setup`, so it exists in the UI before an entry does.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entry"
        )
    return entries[0]


def _refuse(err: ScheduleValueError) -> ServiceValidationError:
    """Turn a pure validation failure into the one HA reports to the caller."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_value",
        translation_placeholders={"field": str(err.field), "value": str(err.value)},
    )


async def _async_set_schedule(call: ServiceCall) -> None:
    """Validate, merge over the stored options, and write once."""
    hass = call.hass
    entry = _entry(hass)

    try:
        stream = validate_stream(call.data[CONF_STREAM])
        changes = validate_changes(call.data)
    except ScheduleValueError as err:
        raise _refuse(err) from err

    options = merge_stream_options(entry.options, stream, changes)
    if options == dict(entry.options):
        # Nothing actually moved. Returning quietly is right -- the call was
        # well formed and the stored schedule already says this -- but the
        # write is skipped so the entry does not reload for no reason.
        return
    hass.config_entries.async_update_entry(entry, options=options)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the domain's actions. Called once, from `async_setup`."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        _async_set_schedule,
        schema=SET_SCHEDULE_SCHEMA,
    )
