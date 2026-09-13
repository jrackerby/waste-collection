"""Pure collection-schedule arithmetic -- no Home Assistant imports, deliberately.

THIS FILE MUST STAY IMPORT-FREE OF `homeassistant.*`, the same obligation
household_state's resolver carries and for the same reason: every answer this
integration gives about a date can then be exercised by inspection, with no
live state, no config entry and no restart.

IT ALSO TAKES NO CLOCK. Every function that needs "today" is handed it. A
function that reads the clock itself cannot be tested by inspection, and the
questions here -- is the truck coming tomorrow, is this the on week -- are
exactly the ones nobody can wait around to observe.

DATES, NOT DATETIMES. Everything below is `datetime.date`. The TypeScript this
was ported from had to round its day arithmetic because a DST boundary makes
one span 23 hours and another 25, and a floor turns "in 7 days" into 6 twice a
year. Calendar arithmetic on `date` has no such hazard -- the rounding is gone
rather than reimplemented, which is the one behavioural difference between the
two and is a simplification, not a change of answer.
"""

from datetime import date, timedelta

from .const import (
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
    PICKUP_HOLIDAY,
    PICKUP_OVERRIDE,
    PICKUP_REGULAR,
)


def schedule_gap(weekday, cadence, anchor):
    """Name the first thing standing between this stream and a date, or None.

    Order matters: a cadence is meaningless without a pickup day, and an
    anchor is meaningless unless the cadence is every-other-week.
    """
    if weekday is None:
        return GAP_DAY
    if cadence is None:
        return GAP_CADENCE
    if cadence == CADENCE_BIWEEKLY and anchor is None:
        return GAP_ANCHOR
    return None


def next_pickups(weekday, cadence, anchor, today, count=1):
    """The next `count` pickup dates, today INCLUDED when today is the day.

    A pickup on the day itself stays upcoming until the day is over: the cart
    goes out the night before and comes back that evening, so rolling to next
    week at midnight would spend the one day that matters announcing that the
    truck comes in seven days.
    """
    if schedule_gap(weekday, cadence, anchor) is not None:
        return []

    first = today + timedelta(days=(weekday - today.weekday()) % 7)

    if cadence == CADENCE_BIWEEKLY:
        # Snap the anchor back to the most recent occurrence of the pickup
        # weekday on or before it, so an anchor entered as "the Friday I saw
        # the truck" still fixes parity for a Wednesday route.
        snapped = anchor - timedelta(days=(anchor.weekday() - weekday) % 7)
        # Both dates now sit on the pickup weekday, so the difference is a
        # whole number of weeks and only its parity is being asked.
        weeks = (first - snapped).days // 7
        if weeks % 2 != 0:
            first += timedelta(days=7)

    step = 14 if cadence == CADENCE_BIWEEKLY else 7
    return [first + timedelta(days=i * step) for i in range(count)]


def week_start(day):
    """The Monday of the week `day` falls in.

    Monday, because that is the week the holiday rule counts over: a holiday
    on a Monday delays every route for the rest of that week, and a holiday
    on a Saturday delays nothing. A Sunday holiday is entered as the Monday it
    is OBSERVED on -- the calendar says which, and nothing here guesses.
    """
    return day - timedelta(days=day.weekday())


def holiday_shift(day, holidays, shift_days):
    """How many days a pickup on `day` moves for the holidays in its week.

    Every holiday in the same Monday-start week ON OR BEFORE the pickup day
    counts once, so a week with two holidays ahead of Friday's route moves it
    twice. A holiday later in the week than the pickup has not happened yet
    when the truck comes and moves nothing.
    """
    if not holidays or not shift_days:
        return 0
    start = week_start(day)
    ahead = sum(1 for h in holidays if start <= h <= day)
    return ahead * shift_days


def resolve_pickups(scheduled, holidays, shift_days, overrides, count):
    """Turn scheduled dates into the pickups that will actually happen.

    Each result is a dict: `date` (when the truck comes), `type` (WHY it is
    that date -- regular, holiday, override) and `scheduled` (the date the
    cadence alone would have given, which differs from `date` only when it
    moved). The list is sorted by resolved date and cut to `count`, so a
    caller wanting `count` real pickups should hand in more scheduled ones
    than that: every skip removes one.

    An OVERRIDE WINS OVER THE HOLIDAY RULE, and is keyed on the SCHEDULED
    date, not the shifted one. A person who says "the 25th is skipped" means
    the pickup the calendar put on the 25th, whatever day the holiday rule
    would have moved it to -- keying on the moved date would make the same
    override land or miss depending on whether the holiday was entered.
    """
    holidays = tuple(holidays or ())
    overrides = dict(overrides or {})
    out = []
    for day in scheduled:
        key = day.isoformat()
        if key in overrides:
            replacement = overrides[key]
            if replacement is None:
                continue  # skipped: the truck is not coming for this one
            out.append({"date": replacement, "type": PICKUP_OVERRIDE, "scheduled": day})
            continue
        shift = holiday_shift(day, holidays, shift_days)
        if shift:
            out.append(
                {"date": day + timedelta(days=shift), "type": PICKUP_HOLIDAY, "scheduled": day}
            )
        else:
            out.append({"date": day, "type": PICKUP_REGULAR, "scheduled": day})
    out.sort(key=lambda r: r["date"])
    return out[:count]


def upcoming_pickups(weekday, cadence, anchor, today, count, holidays=(), shift_days=0, overrides=None):
    """`next_pickups` with the holiday rule and overrides applied, today included.

    Generates enough scheduled dates that every skip and every backward
    shift still leaves `count` results, then drops anything that resolved to
    before today: a pickup the calendar put on Monday and a holiday moved to
    Tuesday is still upcoming on Monday night, and one an override moved
    EARLIER than today is not.
    """
    overrides = overrides or {}
    skips = sum(1 for v in overrides.values() if v is None)
    # One extra cycle of headroom on top of the skips, because an override
    # can move a pickup past the next scheduled one and the cut would
    # otherwise drop a real date to make room for it.
    scheduled = next_pickups(weekday, cadence, anchor, today, count + skips + 1)
    if not scheduled:
        return []
    # A pickup scheduled LAST cycle can still be upcoming if a holiday or an
    # override pushed it past today, so look one cycle back as well.
    step = 14 if cadence == CADENCE_BIWEEKLY else 7
    scheduled.insert(0, scheduled[0] - timedelta(days=step))
    resolved = resolve_pickups(scheduled, holidays, shift_days, overrides, count + 1)
    return [r for r in resolved if r["date"] >= today][:count]


def cart_status(next_pickup, cart_out, today):
    """What the curb cart needs from a person right now.

    `return` is the case worth naming: the cart is still at the curb and the
    next pickup is no longer within a day, which means the truck has already
    been. That is read off the schedule rather than off a collected stamp,
    because the stamp only exists if somebody pressed the button, while the
    cart being out past its own pickup day is true either way.
    """
    if next_pickup is None:
        return CART_OUT if cart_out else CART_UNSCHEDULED
    delta = (next_pickup - today).days
    if cart_out:
        return CART_RETURN if delta > 1 else CART_OUT
    return CART_DUE if delta <= 1 else CART_IDLE


def days_until(target, today):
    """Whole days from `today` to `target`; negative once it is past."""
    return (target - today).days


def weekday_index(name, weekdays):
    """Index of a stored weekday slug, or None when it is unset/unknown.

    Unknown is None rather than an exception: a renamed or hand-edited option
    must leave the schedule unconfigured, never silently pointing at Monday.
    """
    try:
        return weekdays.index(name)
    except ValueError:
        return None


def parse_dates(values):
    """A list of ISO strings (or dates) to a sorted tuple of dates.

    Anything that will not parse is DROPPED, not defaulted -- the same rule
    as `parse_anchor`. A holiday that cannot be read is a holiday that does
    not shift anything, which the person will notice on the day; a holiday
    silently read as some other date moves a route nobody meant to move.
    """
    out = []
    for value in values or ():
        day = parse_anchor(value)
        if day is not None:
            out.append(day)
    return tuple(sorted(set(out)))


def parse_overrides(mapping):
    """A stored `{iso: iso | None}` mapping to `{iso: date | None}`.

    A key that will not parse is dropped; a value that will not parse is
    dropped WITH its key, so a corrupt replacement never turns into a skip.
    """
    out = {}
    for key, value in (mapping or {}).items():
        day = parse_anchor(key)
        if day is None:
            continue
        if value is None:
            out[day.isoformat()] = None
            continue
        replacement = parse_anchor(value)
        if replacement is not None:
            out[day.isoformat()] = replacement
    return out


def parse_anchor(value):
    """An ISO date string to a `date`, or None.

    Anything unparseable is None for the same reason as above -- an anchor
    that cannot be read leaves the cadence unresolved, which the surface
    reports, rather than defaulting to a parity nobody chose.
    """
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
