"""Setup, the schedule options flow, and the receptacle subentry flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CADENCES,
    CONF_ANCHOR,
    CONF_CADENCE,
    CONF_HOLIDAY_SHIFT_DAYS,
    CONF_HOLIDAYS,
    CONF_NAME,
    CONF_STREAM,
    CONF_WEEKDAY,
    DEFAULT_HOLIDAY_SHIFT_DAYS,
    DOMAIN,
    RECEPTACLE_STREAMS,
    SUBENTRY_RECEPTACLE,
    WEEKDAYS,
)
from .schedule_options import (
    MAX_HOLIDAY_SHIFT_DAYS,
    ScheduleValueError,
    validate_holidays,
    validate_shift_days,
)

# EVERY SCHEDULE FIELD IS OPTIONAL, and that is deliberate. An unset pickup
# day has to stay unset: the YAML design this replaces needed a literal
# "Not set" sentinel because an input_select with no initial silently takes
# its first option, and a brand-new install then read as "trash goes out
# Monday" -- indistinguishable from a configured house. A selector that can
# simply be left empty says the same thing without the sentinel.
def _stream_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_WEEKDAY, description={"suggested_value": defaults.get(CONF_WEEKDAY)}
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(WEEKDAYS),
                    translation_key="weekday",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_CADENCE, description={"suggested_value": defaults.get(CONF_CADENCE)}
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(CADENCES),
                    translation_key="cadence",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            # Only read when the cadence is every-other-week. Any date the
            # truck actually came will do -- it fixes WHICH week, nothing else,
            # and the resolver snaps it back to the pickup weekday itself.
            vol.Optional(
                CONF_ANCHOR, description={"suggested_value": defaults.get(CONF_ANCHOR)}
            ): selector.DateSelector(),
        }
    )


def _holidays_schema(options: dict[str, Any]) -> vol.Schema:
    """The entry-level holiday list and shift.

    A multi-value TEXT selector rather than a date selector: the date
    selector is single-valued, and a list of ten holidays as ten steps is a
    form nobody finishes. The strings are validated by the same pure module
    the action uses, so a typo is refused with the field named rather than
    stored as a holiday that never shifts anything.
    """
    return vol.Schema(
        {
            vol.Optional(
                CONF_HOLIDAYS,
                description={"suggested_value": list(options.get(CONF_HOLIDAYS) or [])},
            ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            vol.Optional(
                CONF_HOLIDAY_SHIFT_DAYS,
                default=options.get(CONF_HOLIDAY_SHIFT_DAYS, DEFAULT_HOLIDAY_SHIFT_DAYS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=MAX_HOLIDAY_SHIFT_DAYS, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


class WasteCollectionConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        # single_config_entry in the manifest already blocks a second entry;
        # setup takes nothing because every field has a real "unset" and the
        # schedule is better set once the entry exists and can be edited.
        return self.async_create_entry(title="Waste Collection", data={}, options={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WasteCollectionOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_RECEPTACLE: ReceptacleSubentryFlow}


class WasteCollectionOptionsFlow(OptionsFlow):
    """One step per stream, each writing only its own key.

    MERGING OVER THE EXISTING OPTIONS, NOT REPLACING THEM, is the trap here:
    `async_create_entry(data=...)` replaces `entry.options` wholesale, so a step returning only its own keys deletes every other
    step's, silently. Harmless while a flow has one step -- which is how it
    survives to the commit that adds the second.
    """

    # ONE STEP PER STREAM, spelled out rather than generated: each needs its
    # own translated title, and a third stream means adding a step here and a
    # string in translations/en.json. const.STREAMS stays the list every
    # ENTITY is derived from; this flow is the one place a stream is named
    # twice, and it is named twice because a person reads these two screens.
    def __init__(self) -> None:
        self._collected: dict[str, Any] = {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_trash()

    async def async_step_trash(self, user_input=None):
        if user_input is not None:
            self._collected["trash"] = user_input
            return await self.async_step_recycling()
        return self.async_show_form(
            step_id="trash",
            data_schema=_stream_schema(self.config_entry.options.get("trash", {})),
        )

    async def async_step_recycling(self, user_input=None):
        if user_input is not None:
            self._collected["recycling"] = user_input
            return await self.async_step_holidays()
        return self.async_show_form(
            step_id="recycling",
            data_schema=_stream_schema(self.config_entry.options.get("recycling", {})),
        )

    async def async_step_holidays(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                holidays = validate_holidays(user_input.get(CONF_HOLIDAYS))
                shift = validate_shift_days(
                    user_input.get(CONF_HOLIDAY_SHIFT_DAYS, DEFAULT_HOLIDAY_SHIFT_DAYS)
                )
            except ScheduleValueError as err:
                errors[str(err.field)] = "unknown_value"
            else:
                # Each stream step returned only its own weekday/cadence/
                # anchor; a stream's OVERRIDES live under the same key and
                # were not on that form, so carry them across or the form
                # deletes them.
                merged = dict(self.config_entry.options)
                for stream, fields in self._collected.items():
                    merged[stream] = {**(merged.get(stream) or {}), **fields}
                    for gone in (CONF_WEEKDAY, CONF_CADENCE, CONF_ANCHOR):
                        if gone not in fields:
                            merged[stream].pop(gone, None)
                merged[CONF_HOLIDAYS] = holidays
                merged[CONF_HOLIDAY_SHIFT_DAYS] = shift
                return self.async_create_entry(title="", data=merged)
        return self.async_show_form(
            step_id="holidays",
            data_schema=_holidays_schema(self.config_entry.options),
            errors=errors,
        )


class ReceptacleSubentryFlow(ConfigSubentryFlow):
    """Add or rename one receptacle.

    A bin is a SUBENTRY rather than a row in options because that is what
    gives it its own device, and a device is what can be dropped into an
    area. Assigning the area is left to the normal device UI -- this flow
    does not ask for a room, so there is no second copy of the house's room
    list to drift out of step with the area registry.
    """

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self.async_step_add()

    async def async_step_add(self, user_input=None) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(
            step_id="add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(),
                    vol.Required(CONF_STREAM): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(RECEPTACLE_STREAMS),
                            translation_key="stream",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=subentry.data.get(CONF_NAME, subentry.title)
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_STREAM, default=subentry.data.get(CONF_STREAM)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(RECEPTACLE_STREAMS),
                            translation_key="stream",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )
