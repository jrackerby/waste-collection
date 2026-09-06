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
