"""Holiday shifts and overrides, exercised by inspection.

Same anchors as test_resolver.py: 2026-09-02 is a Wednesday. The US calendar
the rule was written against puts Thanksgiving on 2026-11-26 (Thursday) and
Christmas on 2026-12-25 (Friday); Labor Day 2026 is Monday 2026-09-07.
"""

from datetime import date

import pytest

from waste_collection.const import (
    CADENCE_BIWEEKLY,
    CADENCE_WEEKLY,
    CONF_HOLIDAY_SHIFT_DAYS,
    CONF_HOLIDAYS,
    CONF_OVERRIDES,
    PICKUP_HOLIDAY,
    PICKUP_OVERRIDE,
    PICKUP_REGULAR,
    WEEKDAYS,
)
from waste_collection.resolver import (
    holiday_shift,
    next_pickups,
    parse_dates,
    parse_overrides,
    resolve_pickups,
    upcoming_pickups,
    week_start,
)
from waste_collection.schedule_options import (
    MAX_HOLIDAY_SHIFT_DAYS,
    ScheduleValueError,
    merge_holiday_options,
    merge_override,
    validate_holidays,
    validate_override,
    validate_shift_days,
)

WED = WEEKDAYS.index("wednesday")
FRI = WEEKDAYS.index("friday")
LABOR_DAY = date(2026, 9, 7)  # Monday
THANKSGIVING = date(2026, 11, 26)  # Thursday
CHRISTMAS = date(2026, 12, 25)  # Friday


def test_calendar_facts_the_fixtures_rest_on():
    assert LABOR_DAY.weekday() == 0
    assert THANKSGIVING.weekday() == 3
    assert CHRISTMAS.weekday() == 4


class TestWeekStart:
    def test_monday_is_its_own_start(self):
        assert week_start(LABOR_DAY) == LABOR_DAY

    def test_sunday_belongs_to_the_week_before(self):
        assert week_start(date(2026, 9, 13)) == LABOR_DAY


class TestHolidayShift:
    def test_a_monday_holiday_moves_the_rest_of_its_week(self):
        wed = date(2026, 9, 9)
        assert holiday_shift(wed, (LABOR_DAY,), 1) == 1

    def test_a_holiday_after_the_pickup_moves_nothing(self):
        # Thanksgiving Thursday: a Wednesday route that week is unmoved.
        assert holiday_shift(date(2026, 11, 25), (THANKSGIVING,), 1) == 0
        # A Friday route that week moves.
        assert holiday_shift(date(2026, 11, 27), (THANKSGIVING,), 1) == 1

    def test_the_holiday_itself_moves(self):
        assert holiday_shift(CHRISTMAS, (CHRISTMAS,), 1) == 1

    def test_a_holiday_in_another_week_moves_nothing(self):
        assert holiday_shift(date(2026, 9, 16), (LABOR_DAY,), 1) == 0

    def test_two_holidays_ahead_count_twice(self):
        mon, tue = date(2026, 9, 7), date(2026, 9, 8)
        assert holiday_shift(date(2026, 9, 11), (mon, tue), 1) == 2

    def test_shift_days_scales_and_zero_disables(self):
        assert holiday_shift(date(2026, 9, 9), (LABOR_DAY,), 2) == 2
        assert holiday_shift(date(2026, 9, 9), (LABOR_DAY,), 0) == 0

    def test_no_holidays_is_no_shift(self):
        assert holiday_shift(date(2026, 9, 9), (), 1) == 0
        assert holiday_shift(date(2026, 9, 9), None, 1) == 0


class TestResolvePickups:
    def test_regular_when_nothing_applies(self):
        rows = resolve_pickups([date(2026, 9, 2)], (), 1, {}, 4)
        assert rows == [
            {"date": date(2026, 9, 2), "type": PICKUP_REGULAR, "scheduled": date(2026, 9, 2)}
        ]

    def test_holiday_shift_names_the_scheduled_date(self):
        rows = resolve_pickups([date(2026, 9, 9)], (LABOR_DAY,), 1, {}, 4)
        assert rows == [
            {"date": date(2026, 9, 10), "type": PICKUP_HOLIDAY, "scheduled": date(2026, 9, 9)}
        ]

    def test_override_replaces_and_wins_over_the_holiday_rule(self):
        # The holiday rule would say Thursday; the person says Saturday.
        rows = resolve_pickups(
            [date(2026, 9, 9)], (LABOR_DAY,), 1, {"2026-09-09": date(2026, 9, 12)}, 4
        )
        assert rows == [
            {"date": date(2026, 9, 12), "type": PICKUP_OVERRIDE, "scheduled": date(2026, 9, 9)}
        ]

    def test_override_is_keyed_on_the_scheduled_date_not_the_shifted_one(self):
        # An override on the SHIFTED date does not apply: the key is what the
        # calendar said, so it reads the same whether or not the holiday was
        # entered.
        rows = resolve_pickups(
            [date(2026, 9, 9)], (LABOR_DAY,), 1, {"2026-09-10": date(2026, 9, 12)}, 4
        )
        assert rows[0]["type"] == PICKUP_HOLIDAY
        assert rows[0]["date"] == date(2026, 9, 10)

    def test_skip_removes_the_pickup(self):
        rows = resolve_pickups(
            [date(2026, 9, 2), date(2026, 9, 9)], (), 1, {"2026-09-02": None}, 4
        )
        assert [r["date"] for r in rows] == [date(2026, 9, 9)]

    def test_sorted_by_resolved_date_and_cut_to_count(self):
        # An override pushes the first past the second.
        rows = resolve_pickups(
            [date(2026, 9, 2), date(2026, 9, 9), date(2026, 9, 16)],
            (),
            1,
            {"2026-09-02": date(2026, 9, 11)},
            2,
        )
        assert [r["date"] for r in rows] == [date(2026, 9, 9), date(2026, 9, 11)]


class TestUpcomingPickups:
    def test_matches_next_pickups_when_nothing_applies(self):
        today = date(2026, 9, 2)
        plain = next_pickups(WED, CADENCE_WEEKLY, None, today, 4)
        rows = upcoming_pickups(WED, CADENCE_WEEKLY, None, today, 4)
        assert [r["date"] for r in rows] == plain
        assert {r["type"] for r in rows} == {PICKUP_REGULAR}

    def test_unset_schedule_is_empty(self):
        assert upcoming_pickups(None, CADENCE_WEEKLY, None, date(2026, 9, 2), 4) == []

    def test_a_shifted_pickup_is_still_upcoming_on_its_scheduled_day(self):
        # Labor Day week: Wednesday's route moves to Thursday. On Wednesday
        # night the truck has not come, so it must still be next -- not the
        # following Wednesday.
        today = date(2026, 9, 9)
        rows = upcoming_pickups(WED, CADENCE_WEEKLY, None, today, 4, (LABOR_DAY,), 1)
        assert rows[0]["date"] == date(2026, 9, 10)
        assert rows[0]["type"] == PICKUP_HOLIDAY
        assert rows[0]["scheduled"] == date(2026, 9, 9)

    def test_a_shifted_pickup_from_last_cycle_is_still_upcoming_on_the_shifted_day(self):
        # Thursday of Labor Day week: `next_pickups` alone would say next
        # Wednesday, because this week's Wednesday is past. The truck comes
        # today.
        today = date(2026, 9, 10)
        rows = upcoming_pickups(WED, CADENCE_WEEKLY, None, today, 4, (LABOR_DAY,), 1)
        assert rows[0]["date"] == today
        assert rows[1]["date"] == date(2026, 9, 16)
        assert rows[1]["type"] == PICKUP_REGULAR

    def test_a_skip_still_yields_count_results(self):
        today = date(2026, 9, 2)
        rows = upcoming_pickups(
            WED, CADENCE_WEEKLY, None, today, 4, overrides={"2026-09-09": None}
        )
        assert len(rows) == 4
        assert date(2026, 9, 9) not in [r["date"] for r in rows]
        assert rows[1]["date"] == date(2026, 9, 16)

    def test_an_override_moved_before_today_is_gone(self):
        today = date(2026, 9, 2)
        rows = upcoming_pickups(
            WED, CADENCE_WEEKLY, None, today, 4, overrides={"2026-09-02": date(2026, 9, 1)}
        )
        assert rows[0]["date"] == date(2026, 9, 9)

    def test_biweekly_lookback_uses_the_fortnight(self):
        # Biweekly on Wednesdays, on-week anchored 2026-09-09 (Labor Day week).
        # Thursday the 10th: last cycle's Wednesday (the 9th) moved to today.
        today = date(2026, 9, 10)
        rows = upcoming_pickups(
            WED, CADENCE_BIWEEKLY, date(2026, 9, 9), today, 3, (LABOR_DAY,), 1
        )
        assert [r["date"] for r in rows] == [
            date(2026, 9, 10),
            date(2026, 9, 23),
            date(2026, 10, 7),
        ]

    def test_christmas_friday_route(self):
        today = date(2026, 12, 21)
        rows = upcoming_pickups(FRI, CADENCE_WEEKLY, None, today, 2, (CHRISTMAS,), 1)
        assert rows[0] == {
            "date": date(2026, 12, 26),
            "type": PICKUP_HOLIDAY,
            "scheduled": CHRISTMAS,
        }
        assert rows[1]["date"] == date(2027, 1, 1)
        assert rows[1]["type"] == PICKUP_REGULAR


class TestParsers:
    def test_parse_dates_sorts_dedupes_and_drops_junk(self):
        assert parse_dates(["2026-12-25", "2026-09-07", "nope", "2026-09-07", None]) == (
            LABOR_DAY,
            CHRISTMAS,
        )
        assert parse_dates(None) == ()

    def test_parse_overrides_keeps_skips_and_drops_corrupt_replacements(self):
        assert parse_overrides(
            {"2026-09-02": None, "2026-09-09": "2026-09-10", "2026-09-16": "junk", "junk": None}
        ) == {"2026-09-02": None, "2026-09-09": date(2026, 9, 10)}


class TestValidateHolidays:
    def test_normalises_sorts_and_dedupes(self):
        assert validate_holidays(["2026-12-25", "2026-09-07", "2026-12-25", ""]) == [
            "2026-09-07",
            "2026-12-25",
        ]

    def test_none_is_empty(self):
        assert validate_holidays(None) == []
        assert validate_holidays([]) == []

    def test_a_bare_string_is_refused_not_iterated(self):
        with pytest.raises(ScheduleValueError) as err:
            validate_holidays("2026-12-25")
        assert err.value.field == CONF_HOLIDAYS

    def test_a_bad_date_names_itself(self):
        with pytest.raises(ScheduleValueError) as err:
            validate_holidays(["2026-12-25", "christmas"])
        assert err.value.value == "christmas"

    def test_an_integer_is_refused(self):
        with pytest.raises(ScheduleValueError):
            validate_holidays([20261225])


class TestValidateShiftDays:
    @pytest.mark.parametrize(
        ("value", "expected"), [(0, 0), (1, 1), (6, 6), (1.0, 1), ("2", 2), (" 3 ", 3)]
    )
    def test_accepts_whole_numbers_in_range(self, value, expected):
        assert validate_shift_days(value) == expected

    @pytest.mark.parametrize("value", [-1, MAX_HOLIDAY_SHIFT_DAYS + 1, True, 1.5, "one", None])
    def test_refuses_the_rest(self, value):
        with pytest.raises(ScheduleValueError) as err:
            validate_shift_days(value)
        assert err.value.field == CONF_HOLIDAY_SHIFT_DAYS


class TestMergeHolidayOptions:
    def test_leaves_unmentioned_keys_alone(self):
        options = {"trash": {"weekday": "wednesday"}, CONF_HOLIDAYS: ["2026-09-07"]}
        merged = merge_holiday_options(options, shift_days=2)
        assert merged[CONF_HOLIDAYS] == ["2026-09-07"]
        assert merged[CONF_HOLIDAY_SHIFT_DAYS] == 2
        assert merged["trash"] == {"weekday": "wednesday"}
        assert CONF_HOLIDAY_SHIFT_DAYS not in options  # not mutated

    def test_an_empty_list_is_stored_not_dropped(self):
        merged = merge_holiday_options({CONF_HOLIDAYS: ["2026-09-07"]}, holidays=[])
        assert merged[CONF_HOLIDAYS] == []


class TestValidateOverride:
    def test_replacement(self):
        assert validate_override({"date": "2026-12-23", "replacement": "2026-12-24"}) == (
            "2026-12-23",
            "2026-12-24",
            False,
        )

    def test_skip(self):
        assert validate_override({"date": "2026-12-23", "skip": True}) == (
            "2026-12-23",
            None,
            False,
        )

    def test_clear(self):
        assert validate_override({"date": "2026-12-23", "clear": True}) == (
            "2026-12-23",
            None,
            True,
        )

    def test_skip_and_replacement_contradict(self):
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "2026-12-23", "skip": True, "replacement": "2026-12-24"})

    def test_clear_with_anything_else_is_refused(self):
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "2026-12-23", "clear": True, "skip": True})

    def test_nothing_asked_is_refused(self):
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "2026-12-23"})
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "2026-12-23", "replacement": ""})

    def test_replacement_equal_to_date_is_refused(self):
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "2026-12-23", "replacement": "2026-12-23"})

    def test_missing_or_bad_date_is_refused(self):
        with pytest.raises(ScheduleValueError):
            validate_override({"replacement": "2026-12-24"})
        with pytest.raises(ScheduleValueError):
            validate_override({"date": "xmas", "skip": True})


class TestMergeOverride:
    def test_sets_under_the_stream_and_keeps_the_schedule(self):
        options = {"trash": {"weekday": "wednesday"}, "recycling": {"weekday": "wednesday"}}
        merged = merge_override(options, "trash", "2026-12-23", "2026-12-24", False)
        assert merged["trash"] == {
            "weekday": "wednesday",
            CONF_OVERRIDES: {"2026-12-23": "2026-12-24"},
        }
        assert merged["recycling"] == options["recycling"]
        assert CONF_OVERRIDES not in options["trash"]  # not mutated

    def test_skip_is_a_none_value(self):
        merged = merge_override({}, "trash", "2026-12-23", None, False)
        assert merged["trash"][CONF_OVERRIDES] == {"2026-12-23": None}

    def test_clear_removes_and_drops_an_empty_map(self):
        options = {"trash": {CONF_OVERRIDES: {"2026-12-23": None}}}
        merged = merge_override(options, "trash", "2026-12-23", None, True)
        assert CONF_OVERRIDES not in merged["trash"]

    def test_clear_of_an_absent_date_is_a_no_op(self):
        options = {"trash": {"weekday": "wednesday"}}
        assert merge_override(options, "trash", "2026-12-23", None, True) == options
