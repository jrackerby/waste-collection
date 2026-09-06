"""The collection calendar, exercised by inspection.

Ported from apps/trash-collection/src/lib/waste.test.ts in
jrackerby/ha-dashboards-control, whose 41 assertions defined this behaviour
before the integration existed. The cases that survive the port are the ones
about DATES; the ones about wording and row layout stay on the board, which is
where wording lives.

2026-09-02 is a Wednesday and 2026-09-04 a Friday; every fixture below is
anchored on those two facts.
"""

from datetime import date

from waste_collection.const import (
    CADENCE_BIWEEKLY,
    CADENCE_WEEKLY,
    CART_DUE,
    CART_IDLE,
    CART_OUT,
    CART_RETURN,
    CART_UNSCHEDULED,
    GAP_ANCHOR,
    GAP_CADENCE,
    GAP_DAY,
    WEEKDAYS,
)
from waste_collection.resolver import (
    cart_status,
    next_pickups,
    parse_anchor,
    schedule_gap,
    weekday_index,
)

WED = WEEKDAYS.index("wednesday")
FRI = WEEKDAYS.index("friday")


def test_the_weekday_table_matches_the_stdlib():
    # The whole port rests on this: WEEKDAYS is indexed by date.weekday(),
    # Monday-is-0, NOT JavaScript's Sunday-is-0. If this drifts every date
    # below is wrong by a constant and nothing else here would notice.
    assert date(2026, 9, 2).weekday() == WED
    assert date(2026, 9, 4).weekday() == FRI


class TestScheduleGap:
    def test_names_the_first_field_in_the_way(self):
        assert schedule_gap(None, CADENCE_WEEKLY, None) == GAP_DAY
        assert schedule_gap(WED, None, None) == GAP_CADENCE
        assert schedule_gap(WED, CADENCE_BIWEEKLY, None) == GAP_ANCHOR

    def test_clears_once_the_set_is_complete(self):
        assert schedule_gap(WED, CADENCE_WEEKLY, None) is None
        assert schedule_gap(WED, CADENCE_BIWEEKLY, date(2026, 9, 2)) is None


class TestWeekly:
    def test_returns_today_when_today_is_the_day(self):
        assert next_pickups(WED, CADENCE_WEEKLY, None, date(2026, 9, 2)) == [
            date(2026, 9, 2)
        ]

    def test_walks_forward_a_week_at_a_time(self):
        got = next_pickups(WED, CADENCE_WEEKLY, None, date(2026, 9, 3), 3)
        assert got == [date(2026, 9, 9), date(2026, 9, 16), date(2026, 9, 23)]

    def test_computes_nothing_while_a_field_is_unset(self):
        assert next_pickups(None, CADENCE_WEEKLY, None, date(2026, 9, 3)) == []
        assert next_pickups(WED, None, None, date(2026, 9, 3)) == []
        assert next_pickups(WED, CADENCE_BIWEEKLY, None, date(2026, 9, 3)) == []

    def test_crosses_a_dst_boundary_without_losing_a_day(self):
        # US DST ends 1 Nov 2026. The TypeScript had to round its day maths
        # here; `date` arithmetic is immune, and this pins that it stays so.
        got = next_pickups(WED, CADENCE_WEEKLY, None, date(2026, 10, 28), 2)
        assert got == [date(2026, 10, 28), date(2026, 11, 4)]
        assert (got[1] - got[0]).days == 7


class TestBiweekly:
    # Anchored on Wed 2 Sep 2026: 16 Sep is on, 9 Sep is off.
    ANCHOR = date(2026, 9, 2)

    def test_keeps_the_anchors_parity(self):
        got = next_pickups(WED, CADENCE_BIWEEKLY, self.ANCHOR, date(2026, 9, 3), 3)
        assert got == [date(2026, 9, 16), date(2026, 9, 30), date(2026, 10, 14)]

    def test_skips_the_off_week_not_the_on_one(self):
        got = next_pickups(WED, CADENCE_BIWEEKLY, self.ANCHOR, date(2026, 9, 9))
        assert got == [date(2026, 9, 16)]

    def test_holds_parity_across_a_year_boundary(self):
        # 30 Dec 2026 is a Wednesday, 17 weeks after the anchor -- odd, so off.
        got = next_pickups(WED, CADENCE_BIWEEKLY, self.ANCHOR, date(2026, 12, 30))
        assert got == [date(2027, 1, 6)]

    def test_accepts_an_anchor_not_on_the_pickup_weekday(self):
        # "The Friday I noticed the truck" on a Wednesday route must snap back
        # to that week's Wednesday, not invert the parity.
        friday = date(2026, 9, 4)
        got = next_pickups(WED, CADENCE_BIWEEKLY, friday, date(2026, 9, 3), 2)
        assert got == [date(2026, 9, 16), date(2026, 9, 30)]

    def test_reads_a_future_anchor_the_same_as_a_past_one(self):
        # 3 Mar 2027 is a Wednesday an even number of weeks from 16 Sep 2026.
        future = date(2027, 3, 3)
        got = next_pickups(WED, CADENCE_BIWEEKLY, future, date(2026, 9, 3))
        assert got == [date(2026, 9, 16)]

    def test_an_anchor_before_the_snap_still_parses_as_whole_weeks(self):
        # Regression guard for the floor-vs-round trap: when `first` is
        # EARLIER than the snapped anchor the week count goes negative, and
        # Python's // floors toward minus infinity. Parity must survive that.
        late_anchor = date(2027, 6, 2)
        got = next_pickups(WED, CADENCE_BIWEEKLY, late_anchor, date(2026, 9, 3))
        assert (got[0] - date(2027, 6, 2)).days % 14 == 0


class TestCartStatus:
    TODAY = date(2026, 9, 3)

    def test_asks_for_the_cart_the_day_before_and_on_the_day(self):
        assert cart_status(date(2026, 9, 4), False, self.TODAY) == CART_DUE
        assert cart_status(date(2026, 9, 3), False, self.TODAY) == CART_DUE

    def test_is_quiet_the_rest_of_the_week(self):
        assert cart_status(date(2026, 9, 9), False, self.TODAY) == CART_IDLE

    def test_asks_for_the_cart_back_once_its_pickup_has_passed(self):
        assert cart_status(date(2026, 9, 9), True, self.TODAY) == CART_RETURN

    def test_leaves_an_out_cart_alone_through_its_own_window(self):
        assert cart_status(date(2026, 9, 4), True, self.TODAY) == CART_OUT
        assert cart_status(date(2026, 9, 3), True, self.TODAY) == CART_OUT

    def test_does_not_invent_a_schedule_it_does_not_have(self):
        assert cart_status(None, False, self.TODAY) == CART_UNSCHEDULED
        assert cart_status(None, True, self.TODAY) == CART_OUT


class TestReadingStoredValues:
    def test_an_unset_or_unknown_weekday_is_none_never_monday(self):
        # The failure this refuses: a renamed option silently resolving to
        # index 0 and the house being told trash goes out Monday.
        assert weekday_index("wednesday", WEEKDAYS) == WED
        assert weekday_index(None, WEEKDAYS) is None
        assert weekday_index("Not set", WEEKDAYS) is None
        assert weekday_index("mittwoch", WEEKDAYS) is None

    def test_an_unparseable_anchor_is_none_never_the_epoch(self):
        assert parse_anchor("2026-09-02") == date(2026, 9, 2)
        assert parse_anchor(date(2026, 9, 2)) == date(2026, 9, 2)
        assert parse_anchor(None) is None
        assert parse_anchor("") is None
        assert parse_anchor("not a date") is None

    def test_an_unset_weekday_leaves_the_schedule_uncomputable(self):
        # The pair that matters: a bad stored value must reach next_pickups as
        # a gap, not as a confident wrong date.
        idx = weekday_index("Not set", WEEKDAYS)
        assert schedule_gap(idx, CADENCE_WEEKLY, None) == GAP_DAY
        assert next_pickups(idx, CADENCE_WEEKLY, None, date(2026, 9, 3)) == []


class TestPurity:
    """LAW §11: the resolver imports nothing from `homeassistant`.

    Asserted here rather than left to a docstring, because the whole reason
    the calendar arithmetic lives in its own module is that it can be
    exercised with core absent. The suite itself is the proof -- it is
    collected and run with Home Assistant not installed -- and these two
    assertions make the claim legible instead of implicit.
    """

    def test_home_assistant_is_genuinely_absent_from_this_run(self):
        # If core WERE importable here, the purity the rest of this class
        # checks would be vacuous: an offending import would simply succeed.
        import importlib.util

        assert importlib.util.find_spec("homeassistant") is None, (
            "homeassistant is installed in this environment, so this suite no "
            "longer proves the resolver runs without it"
        )

    def test_neither_pure_module_IMPORTS_home_assistant(self):
        # ON THE IMPORT NODES, NOT ON THE TEXT (LAW §4: assert on code forms,
        # strip comments first). The first version of this grepped the source
        # and failed on resolver.py's own docstring, which says in prose that
        # it must never import core -- a file documenting the rule matching
        # the check for the rule's violation.
        import ast
        import pathlib

        import waste_collection.const as const_mod
        import waste_collection.resolver as resolver_mod

        for mod in (const_mod, resolver_mod):
            tree = ast.parse(pathlib.Path(mod.__file__).read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imported.add(node.module.split(".")[0])
            assert "homeassistant" not in imported, (
                f"{mod.__name__} imports homeassistant: {sorted(imported)}"
            )
