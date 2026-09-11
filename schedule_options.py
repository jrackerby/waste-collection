"""Validating and merging a schedule change -- pure, no Home Assistant imports.

THIS FILE MUST STAY IMPORT-FREE OF `homeassistant.*`, the obligation
resolver.py carries and for the same reason. The guarantee this module exists
to give is a REFUSAL -- an unrecognised weekday or cadence must not reach the
options dict -- and a refusal is only worth as much as the test that proves it
fires. With Home Assistant absent from the suite (tests/conftest.py) the only
way to test it is to keep it here, out of the voluptuous schema that would
otherwise own it.

WHY THE SERVICE VALIDATES AT ALL when the options flow's selectors already
constrain the same three fields to the same values. A dropdown cannot emit a
value that is not in it; `callService` can send anything. GH-618 added this
service precisely so a wall panel could set the schedule without opening
Settings, and TOOLS.md records that a service call answers 200 on a no-op --
so an unrecognised weekday that was quietly dropped, or quietly defaulted to
Monday, would read as success from the one surface that cannot check.

`weekday_index()` in resolver.py is the model: unknown is None, never Monday.
The difference is only in who is told. The resolver is reducing options that
are already stored and reports the gap on the entity; this module is standing
at the door, where there is still a caller to say no to.
"""

from datetime import date

from .const import (
    CADENCES,
    CONF_ANCHOR,
    CONF_CADENCE,
    CONF_WEEKDAY,
    STREAMS,
    WEEKDAYS,
)

# The three fields a schedule change may carry. `stream` is not among them --
# it selects WHICH schedule is being changed and is validated separately.
SCHEDULE_FIELDS = (CONF_WEEKDAY, CONF_CADENCE, CONF_ANCHOR)

# What a caller sends to clear a field rather than set it. Both spellings are
# accepted because they arrive from different places: a JSON `null` from a
# board's `callService`, and an empty string from a UI selector that was
# emptied. Neither is "leave it alone" -- OMITTING the key is that, and the
# distinction is the whole reason this module reads `changes` by key presence
# rather than by truthiness.
CLEARING = (None, "")


class ScheduleValueError(ValueError):
    """A field was present but its value is not one this integration knows.

    Carries the field and the offending value so the caller can be told which
    of the three was wrong -- "invalid schedule" on a wall panel names nothing
    the person can go and fix.
    """

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field}: {value!r}")


def validate_stream(stream):
    """Return the stream slug, or raise. Never falls back to a default."""
    if stream not in STREAMS:
        raise ScheduleValueError("stream", stream)
    return stream


def _validate_anchor(value):
    """An ISO date string or a `date` -> ISO string. Anything else raises.

    Stored as a STRING, not a `date`: options are persisted to
    `.storage/core.config_entries` as JSON, and a `date` is not JSON
    serialisable. `parse_anchor()` reads either, so the resolver does not care
    -- but the writer has to pick one, and the one that survives a restart is
    the string.
    """
    if isinstance(value, date):
        return value.isoformat()
    # ONLY a `date` or a STRING. Not `str(value)` on whatever arrived: from
    # Python 3.11 `date.fromisoformat` also accepts ISO 8601 BASIC format, so
    # the integer 20260904 parses cleanly as 2026-09-04 -- a caller that sent
    # a number by mistake would have it silently coerced into a real schedule.
    # `True` would be rejected by the parse but is an int too, and a type that
    # is not a date is not a date regardless of how it stringifies.
    if not isinstance(value, str):
        raise ScheduleValueError(CONF_ANCHOR, value)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ScheduleValueError(CONF_ANCHOR, value) from None


def validate_changes(raw):
    """Normalise a mapping of field -> value, raising on any value not known.

    Only keys actually present in `raw` appear in the result: a caller setting
    the cadence alone must not thereby clear the pickup day. Clearing is
    explicit and is represented by a None in the returned mapping.
    """
    changes = {}
    for field in SCHEDULE_FIELDS:
        if field not in raw:
            continue
        value = raw[field]
        if any(value is c or value == c for c in CLEARING):
            changes[field] = None
            continue
        if field == CONF_WEEKDAY:
            if value not in WEEKDAYS:
                raise ScheduleValueError(CONF_WEEKDAY, value)
            changes[field] = value
        elif field == CONF_CADENCE:
            if value not in CADENCES:
                raise ScheduleValueError(CONF_CADENCE, value)
            changes[field] = value
        else:
            changes[field] = _validate_anchor(value)
    return changes


def merge_stream_options(options, stream, changes):
    """Return a NEW options mapping with `changes` applied to one stream.

    MERGING AT BOTH LEVELS, and both matter. The outer merge is the trap
    TOOLS.md records for options flows -- replacing `entry.options` wholesale
    drops the other stream's schedule silently. The inner merge is the same
    hazard one level down: a call that sets only the cadence must leave the
    pickup day and the anchor where they were, or setting one field from the
    wall quietly unsets the two beside it.

    Nothing is mutated in place. `async_update_entry` compares the mapping it
    is handed against the stored one to decide whether anything changed, so
    editing the live dict and passing it back is a write that reports success
    and reloads nothing.
    """
    current = dict((options or {}).get(stream) or {})
    for field, value in changes.items():
        if value is None:
            current.pop(field, None)
        else:
            current[field] = value
    merged = dict(options or {})
    merged[stream] = current
    return merged
