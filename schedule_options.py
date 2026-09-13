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
value that is not in it; `callService` can send anything. This service exists
precisely so a dashboard or a script can set the schedule without opening
Settings, and Home Assistant answers a service call 200 even when the call did
nothing -- so an unrecognised weekday that was quietly dropped, or quietly
defaulted to Monday, would read as success from the one surface that cannot
check.

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
    CONF_CLEAR,
    CONF_DATE,
    CONF_HOLIDAY_SHIFT_DAYS,
    CONF_HOLIDAYS,
    CONF_OVERRIDES,
    CONF_REPLACEMENT,
    CONF_SKIP,
    CONF_WEEKDAY,
    STREAMS,
    WEEKDAYS,
)

# The holiday rule's shift is bounded: a route does not move a week for one
# holiday, and a shift of seven or more days lands on or past the NEXT
# scheduled pickup, which is two trucks on one day.
MAX_HOLIDAY_SHIFT_DAYS = 6

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

    MERGING AT BOTH LEVELS, and both matter. The outer merge is the options-flow
    trap: `async_create_entry(data=...)` replaces `entry.options` wholesale, so
    returning one stream's keys drops the other stream's schedule silently. The
    inner merge is the same hazard one level down: a call that sets only the
    cadence must leave the pickup day and the anchor where they were, or setting
    one field from a dashboard quietly unsets the two beside it.

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


# -- holidays: entry-level, one list for every stream ----------------------


def validate_holidays(values):
    """A list of ISO date strings -> sorted, de-duplicated ISO strings.

    A single string is refused rather than iterated: `"2026-12-25"` would
    otherwise validate as ten one-character dates and fail on the first, and
    the error would name `2`, not the field. Anything that is not a date
    raises, naming the offending value -- a holiday silently dropped is a
    route silently not moved.
    """
    if values is None:
        return []
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ScheduleValueError(CONF_HOLIDAYS, values)
    out = set()
    for value in values:
        if any(value is c or value == c for c in CLEARING):
            continue
        out.add(_validate_anchor(value))
    return sorted(out)


def validate_shift_days(value):
    """An integer 0..MAX_HOLIDAY_SHIFT_DAYS, or raise.

    `bool` is an int in Python and `True` would read as one day; refused
    explicitly. A float that is whole is accepted because a JSON number
    from a board arrives as one.
    """
    if isinstance(value, bool):
        raise ScheduleValueError(CONF_HOLIDAY_SHIFT_DAYS, value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int) or not 0 <= value <= MAX_HOLIDAY_SHIFT_DAYS:
        raise ScheduleValueError(CONF_HOLIDAY_SHIFT_DAYS, value)
    return value


def merge_holiday_options(options, holidays=None, shift_days=None):
    """Return a NEW options mapping with the holiday settings applied.

    Same discipline as `merge_stream_options`: keys not passed are left as
    they were, and nothing is mutated in place. An empty holiday list is a
    real value (no holidays) and is stored, not popped -- clearing is what a
    person asks for when the year's list is wrong.
    """
    merged = dict(options or {})
    if holidays is not None:
        merged[CONF_HOLIDAYS] = list(holidays)
    if shift_days is not None:
        merged[CONF_HOLIDAY_SHIFT_DAYS] = shift_days
    return merged


# -- overrides: per stream, keyed on the SCHEDULED date ---------------------


def validate_override(raw):
    """One override call -> (scheduled_iso, replacement_iso | None, clear).

    Three shapes, and only three:
      - `date` + `replacement`: the pickup scheduled for `date` happens on
        `replacement` instead.
      - `date` + `skip: true`: it does not happen at all. Stored as None.
      - `date` + `clear: true`: forget any override on that date.
    A call with `skip` AND a `replacement` is refused: the two contradict
    and picking one would make the other read as accepted. A `replacement`
    equal to `date` is refused too -- it is a no-op that would sit in the
    map claiming to be an override.
    """
    if CONF_DATE not in raw:
        raise ScheduleValueError(CONF_DATE, None)
    day = _validate_anchor(raw[CONF_DATE])
    skip = bool(raw.get(CONF_SKIP, False))
    clear = bool(raw.get(CONF_CLEAR, False))
    replacement = raw.get(CONF_REPLACEMENT)
    has_replacement = not any(replacement is c or replacement == c for c in CLEARING)

    if clear:
        if skip or has_replacement:
            raise ScheduleValueError(CONF_CLEAR, raw)
        return day, None, True
    if skip:
        if has_replacement:
            raise ScheduleValueError(CONF_SKIP, raw)
        return day, None, False
    if not has_replacement:
        # Neither skip nor replacement nor clear: nothing was asked for.
        raise ScheduleValueError(CONF_REPLACEMENT, replacement)
    replacement = _validate_anchor(replacement)
    if replacement == day:
        raise ScheduleValueError(CONF_REPLACEMENT, replacement)
    return day, replacement, False


def merge_override(options, stream, day, replacement, clear):
    """Return a NEW options mapping with one override set or removed."""
    current = dict((options or {}).get(stream) or {})
    overrides = dict(current.get(CONF_OVERRIDES) or {})
    if clear:
        overrides.pop(day, None)
    else:
        overrides[day] = replacement
    if overrides:
        current[CONF_OVERRIDES] = overrides
    else:
        current.pop(CONF_OVERRIDES, None)
    merged = dict(options or {})
    merged[stream] = current
    return merged
