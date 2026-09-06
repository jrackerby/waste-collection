# Waste Collection

A Home Assistant integration for the household's waste: where the bins are,
which ones are holding waste, and when each stream is collected.

Built for [jrackerby/HA](https://github.com/jrackerby/HA) and submoduled there
as `custom_components/waste_collection`. Tracked in jrackerby/HA#610.

## What it publishes

**Per stream** (`trash`, `recycling`) — one device each:

| entity | notes |
|---|---|
| `sensor.*_next_pickup` | `device_class: timestamp`. Attributes carry the exact date, the next four, and `gap` — which field is missing when there is no date |
| `sensor.*_last_collected` | stamped by the button |
| `binary_sensor.*_setout_due` | on the day before and the day of. `status` in its attributes carries the case a boolean cannot: a cart still out the day *after* pickup needs bringing in |
| `switch.*_cart_out` | where the cart physically is — not an instruction |
| `button.*_collected` | the truck came: stamps the time and brings the cart in, because that is one event |

**Per receptacle** — a config subentry, so each is its own device you assign to
an area: `switch.*_has_waste`, `sensor.*_last_emptied`, `button.*_emptied`.

Plus `sensor.waste_collection_active_receptacles`, counting the bins holding
waste with the longest-waiting named first.

## Setup

Add the integration, then **Configure** for each stream's pickup day and
cadence, and **Add receptacle** for each bin.

Every schedule field can be left empty. Nothing is guessed: with no pickup day
the next-pickup sensor is `unknown` and its `gap` attribute says which field is
missing, rather than showing a date nobody chose. The YAML design this replaced
needed a literal `Not set` option for the same reason — an `input_select` with
no `initial` silently takes its first option, so a fresh install read as "trash
goes out Monday", indistinguishable from a configured house.

### Every other week

Set the cadence to every-other-week and give **any date the truck actually
came**. It fixes which week is the on week and nothing else; the resolver snaps
it back to the pickup weekday itself, so "the Friday I noticed them" works fine
for a Wednesday route.

## Design

`resolver.py` holds every date answer and **imports nothing from
`homeassistant`** (LAW §11). It also takes no clock — `today` is always passed
in, because a function that reads the clock cannot be tested by inspection, and
"is the truck coming tomorrow" is exactly the question nobody can wait around
to observe.

The test suite runs with Home Assistant **absent**, which is what makes that
claim real rather than documentary: any core import creeping into `const.py` or
`resolver.py` fails collection on the commit that adds it. `validate.yml`'s
`imports` job covers the other half — the real layout against real core, on
Python 3.14, which is what Home Assistant 2026.x requires (`>=3.14.2`).

Everything is `datetime.date`. The TypeScript this was ported from had to round
its day arithmetic, because a DST boundary makes one span 23 hours and another
25 and a floor turns "in 7 days" into 6 twice a year. Calendar arithmetic has no
such hazard, so the rounding is gone rather than reimplemented — the one
behavioural difference between the two, and a simplification, not a change of
answer.

## Tests

```sh
pip install pytest && ./tools/run_tests.sh
```
