"""Names and constants for the waste_collection integration.

Everything the resolver and the platforms agree on lives here, so a stream
or a cadence is spelled in exactly one place.
"""

DOMAIN = "waste_collection"

# The streams with a curb cart and a schedule. Adding one is this tuple plus
# a translation string -- every entity id and every device is derived from the
# slug, and no platform hardcodes a stream.
STREAM_TRASH = "trash"
STREAM_RECYCLING = "recycling"
STREAMS = (STREAM_TRASH, STREAM_RECYCLING)

# Receptacle streams may include ones with no curb pickup (a compost pail
# emptied into a bin outside), so this is deliberately a superset of STREAMS.
RECEPTACLE_STREAMS = STREAMS

CADENCE_WEEKLY = "weekly"
CADENCE_BIWEEKLY = "biweekly"
CADENCES = (CADENCE_WEEKLY, CADENCE_BIWEEKLY)

# Indexed by date.weekday() -- Monday is 0, matching the stdlib rather than
# JavaScript's Sunday-is-0. The board this replaces used the JS convention;
# anything crossing the boundary converts, and nothing here assumes.
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# What is stopping a next-pickup date from being computable. Named rather than
# boolean because the surface tells the reader which field to go and set, and
# "no date" with no reason is indistinguishable from a broken integration.
GAP_DAY = "day"
GAP_CADENCE = "cadence"
GAP_ANCHOR = "anchor"

# What the curb cart needs from a person right now.
CART_DUE = "due"
CART_OUT = "out"
CART_RETURN = "return"
CART_IDLE = "idle"
CART_UNSCHEDULED = "unscheduled"

CONF_STREAM = "stream"
CONF_WEEKDAY = "weekday"
CONF_CADENCE = "cadence"
CONF_ANCHOR = "anchor"
CONF_ROOM = "room"
CONF_NAME = "name"

# Holiday shifting is ENTRY-LEVEL, not per stream: a municipal holiday moves
# every route in the house by the same rule, so it is stored once beside the
# stream keys rather than copied into each. Overrides ARE per stream -- a
# skipped recycling week says nothing about trash.
CONF_HOLIDAYS = "holidays"
CONF_HOLIDAY_SHIFT_DAYS = "holiday_shift_days"
CONF_OVERRIDES = "overrides"
CONF_DATE = "date"
CONF_REPLACEMENT = "replacement"
CONF_SKIP = "skip"
CONF_CLEAR = "clear"

# How far a pickup moves for each holiday earlier in its week. One day is the
# rule nearly every municipal calendar publishes; it is a setting because
# "nearly" is not "every".
DEFAULT_HOLIDAY_SHIFT_DAYS = 1

# Why the next pickup falls on the date it does. On the entity so a surface
# can say "moved for the holiday" instead of leaving a reader to work out why
# Thursday is not Wednesday.
PICKUP_REGULAR = "regular"
PICKUP_HOLIDAY = "holiday"
PICKUP_OVERRIDE = "override"

SUBENTRY_RECEPTACLE = "receptacle"

# How many upcoming dates the next-pickup sensor carries as an attribute.
UPCOMING_COUNT = 4
