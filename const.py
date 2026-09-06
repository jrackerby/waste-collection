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

SUBENTRY_RECEPTACLE = "receptacle"

# How many upcoming dates the next-pickup sensor carries as an attribute.
UPCOMING_COUNT = 4
