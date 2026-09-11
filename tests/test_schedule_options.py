"""The refusal, and the two-level merge, exercised with Home Assistant absent.

The guarantee under test is GH-618's condition on the action existing at all:
it must reject a weekday or cadence it does not recognise rather than silently
defaulting, because TOOLS.md records that a service call answers 200 on a
no-op and a wall panel therefore cannot tell a stored schedule from an ignored
one.

Every test below states what a FAILURE would look like on the wall, not just
what the function returns, because that is the thing worth protecting.
"""

from datetime import date

import pytest
from waste_collection.const import (
    CADENCE_BIWEEKLY,
    CADENCE_WEEKLY,
    CONF_ANCHOR,
    CONF_CADENCE,
    CONF_WEEKDAY,
    STREAM_RECYCLING,
    STREAM_TRASH,
    WEEKDAYS,
)
from waste_collection.schedule_options import (
    ScheduleValueError,
    merge_stream_options,
    validate_changes,
    validate_stream,
)

# --------------------------------------------------------------------------
# The refusal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["Monday", "mon", "monday ", "", None, 0, "someday", "wednesdayy"],
)
def test_unknown_weekday_raises_rather_than_defaulting(bad):
    """A weekday that is not a slug must never resolve to one.

    "" and None are the two CLEARING spellings and are handled separately --
    they are asserted here only to pin that they never become a day either.
    """
    if bad in ("", None):
        assert validate_changes({CONF_WEEKDAY: bad}) == {CONF_WEEKDAY: None}
        return
    with pytest.raises(ScheduleValueError) as err:
        validate_changes({CONF_WEEKDAY: bad})
    assert err.value.field == CONF_WEEKDAY


@pytest.mark.parametrize("bad", ["Weekly", "every week", "fortnightly", 2, "biweekly "])
def test_unknown_cadence_raises(bad):
    with pytest.raises(ScheduleValueError) as err:
        validate_changes({CONF_CADENCE: bad})
    assert err.value.field == CONF_CADENCE


@pytest.mark.parametrize(
    "bad", ["not-a-date", "2026-13-01", "09/04/2026", "2026-09-31", True, 20260904]
)
def test_unparseable_anchor_raises(bad):
    with pytest.raises(ScheduleValueError) as err:
        validate_changes({CONF_ANCHOR: bad})
    assert err.value.field == CONF_ANCHOR


def test_self_test_the_refusal_can_fail():
    """Proof the assertions above CAN fail -- LAW §4.

    A validator that accepted everything would pass every `raises` test above
    only if those tests were wrong about the input. This asserts the opposite
    direction: the KNOWN-GOOD values do not raise, so the parametrised cases
    are discriminating between good and bad rather than rejecting everything.
    """
    for day in WEEKDAYS:
        assert validate_changes({CONF_WEEKDAY: day}) == {CONF_WEEKDAY: day}
    for cadence in (CADENCE_WEEKLY, CADENCE_BIWEEKLY):
        assert validate_changes({CONF_CADENCE: cadence}) == {CONF_CADENCE: cadence}

    # And the converse: a validator that raised on everything would fail here.
    with pytest.raises(ScheduleValueError):
        validate_changes({CONF_WEEKDAY: "not-a-day"})


def test_validate_stream_refuses_unknown():
    assert validate_stream(STREAM_TRASH) == STREAM_TRASH
    with pytest.raises(ScheduleValueError):
        validate_stream("compost")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def test_anchor_accepts_date_and_iso_and_stores_a_string():
    """A `date` is not JSON serialisable; options are persisted as JSON."""
    for given in (date(2026, 9, 4), "2026-09-04"):
        got = validate_changes({CONF_ANCHOR: given})
        assert got == {CONF_ANCHOR: "2026-09-04"}
        assert isinstance(got[CONF_ANCHOR], str)


def test_absent_key_is_not_a_change():
    """Omitting a field must not clear it -- that is what CLEARING is for."""
    assert validate_changes({}) == {}
    assert validate_changes({CONF_CADENCE: CADENCE_WEEKLY}) == {
        CONF_CADENCE: CADENCE_WEEKLY
    }


@pytest.mark.parametrize("clearer", [None, ""])
def test_explicit_clear_is_distinct_from_omission(clearer):
    assert validate_changes({CONF_WEEKDAY: clearer}) == {CONF_WEEKDAY: None}


# --------------------------------------------------------------------------
# The two-level merge
# --------------------------------------------------------------------------


def test_setting_one_stream_leaves_the_other_intact():
    """The outer merge. TOOLS.md's options-flow trap, one level up."""
    options = {
        STREAM_TRASH: {CONF_WEEKDAY: "wednesday", CONF_CADENCE: CADENCE_WEEKLY},
        STREAM_RECYCLING: {CONF_WEEKDAY: "friday", CONF_CADENCE: CADENCE_BIWEEKLY},
    }
    merged = merge_stream_options(options, STREAM_TRASH, {CONF_WEEKDAY: "monday"})
    assert merged[STREAM_RECYCLING] == options[STREAM_RECYCLING]
    assert merged[STREAM_TRASH][CONF_WEEKDAY] == "monday"


def test_setting_one_field_leaves_the_others_in_that_stream():
    """The inner merge. Setting the cadence must not unset the pickup day."""
    options = {
        STREAM_TRASH: {
            CONF_WEEKDAY: "wednesday",
            CONF_CADENCE: CADENCE_WEEKLY,
            CONF_ANCHOR: "2026-09-02",
        }
    }
    merged = merge_stream_options(
        options, STREAM_TRASH, {CONF_CADENCE: CADENCE_BIWEEKLY}
    )
    assert merged[STREAM_TRASH] == {
        CONF_WEEKDAY: "wednesday",
        CONF_CADENCE: CADENCE_BIWEEKLY,
        CONF_ANCHOR: "2026-09-02",
    }


def test_clearing_removes_the_key_entirely():
    """Absent, not present-and-None: the resolver reads `.get()` and a stored
    None would be indistinguishable from unset anyway -- but an options dict
    carrying explicit nulls is one the options FLOW would then re-offer as a
    suggested value."""
    options = {STREAM_TRASH: {CONF_WEEKDAY: "wednesday", CONF_CADENCE: CADENCE_WEEKLY}}
    merged = merge_stream_options(options, STREAM_TRASH, {CONF_WEEKDAY: None})
    assert CONF_WEEKDAY not in merged[STREAM_TRASH]
    assert merged[STREAM_TRASH][CONF_CADENCE] == CADENCE_WEEKLY


def test_merge_does_not_mutate_the_stored_mapping():
    """`async_update_entry` diffs what it is handed against what is stored.

    Mutating the live dict and handing it back is a write that compares equal,
    reports success, and reloads nothing -- the schedule would appear to save
    from the wall and the entities would keep the old dates until a restart.
    """
    options = {STREAM_TRASH: {CONF_WEEKDAY: "wednesday"}}
    before = {STREAM_TRASH: {CONF_WEEKDAY: "wednesday"}}
    merged = merge_stream_options(options, STREAM_TRASH, {CONF_WEEKDAY: "monday"})
    assert options == before, "input mapping was mutated"
    assert merged is not options
    assert merged[STREAM_TRASH] is not options[STREAM_TRASH]


def test_merge_onto_empty_options_creates_the_stream():
    for empty in ({}, None):
        merged = merge_stream_options(empty, STREAM_TRASH, {CONF_WEEKDAY: "monday"})
        assert merged == {STREAM_TRASH: {CONF_WEEKDAY: "monday"}}


def test_round_trip_matches_what_the_resolver_reads():
    """The written shape is the shape `_reduce_stream` reads back.

    `weekday_index` looks the slug up in WEEKDAYS and `parse_anchor` reads an
    ISO string, so this asserts the writer and the reader agree rather than
    each being separately self-consistent.
    """
    from waste_collection.resolver import parse_anchor, weekday_index

    changes = validate_changes(
        {
            CONF_WEEKDAY: "wednesday",
            CONF_CADENCE: CADENCE_BIWEEKLY,
            CONF_ANCHOR: date(2026, 9, 2),
        }
    )
    stored = merge_stream_options({}, STREAM_TRASH, changes)[STREAM_TRASH]

    assert weekday_index(stored[CONF_WEEKDAY], WEEKDAYS) == 2
    assert parse_anchor(stored[CONF_ANCHOR]) == date(2026, 9, 2)
    assert stored[CONF_CADENCE] == CADENCE_BIWEEKLY
