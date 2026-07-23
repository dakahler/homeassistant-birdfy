"""Config flow for Birdfy integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BirdfyHighlightsApi, BirdfyRecapApi
from .const import (
    DOMAIN,
    CONF_UUID,
    CONF_RECAP_UUID,
    CONF_DATE_RANGE,
    CONF_SUBENTRY_NAME,
    DEFAULT_DATE_RANGE,
    DATE_RANGE_OPTIONS,
    SUBENTRY_TYPE_DATE_RANGE,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UUID): str,
        vol.Optional(CONF_RECAP_UUID, default=""): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    # Validate highlights UUID (required)
    api = BirdfyHighlightsApi(data[CONF_UUID], session)
    if not await api.async_validate_uuid():
        raise InvalidUUID

    # Validate recap UUID if provided (optional)
    recap_uuid = data.get(CONF_RECAP_UUID, "").strip()
    if recap_uuid:
        recap_api = BirdfyRecapApi(recap_uuid, session)
        if not await recap_api.async_validate_uuid():
            raise InvalidRecapUUID

    # Return info to store in the config entry
    return {"title": f"Birdfy ({data[CONF_UUID][:8]}...)"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Birdfy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidUUID:
                errors["base"] = "invalid_uuid"
            except InvalidRecapUUID:
                errors["base"] = "invalid_recap_uuid"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_UUID])
                self._abort_if_unique_id_configured()

                # Clean up empty recap UUID
                if not user_input.get(CONF_RECAP_UUID, "").strip():
                    user_input.pop(CONF_RECAP_UUID, None)

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "highlight_url": "https://highlight.birdfy.com/?uuid=YOUR_UUID",
                "recap_url": "https://recap.birdfy.com/?uuid=YOUR_UUID",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_DATE_RANGE: DateRangeSubentryFlowHandler}


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow to update UUIDs."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            # Validate highlights UUID (required)
            uuid = user_input.get(CONF_UUID, "").strip()
            if not uuid:
                errors["base"] = "invalid_uuid"
            else:
                api = BirdfyHighlightsApi(uuid, session)
                if not await api.async_validate_uuid():
                    errors["base"] = "invalid_uuid"

            # Validate recap UUID if provided
            recap_uuid = user_input.get(CONF_RECAP_UUID, "").strip()
            if not errors and recap_uuid:
                recap_api = BirdfyRecapApi(recap_uuid, session)
                if not await recap_api.async_validate_uuid():
                    errors["base"] = "invalid_recap_uuid"

            # Ensure the new highlights UUID isn't already used by another entry
            if not errors and uuid != self.config_entry.data.get(CONF_UUID):
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        entry.entry_id != self.config_entry.entry_id
                        and entry.data.get(CONF_UUID) == uuid
                    ):
                        errors["base"] = "already_configured"
                        break

            if not errors:
                # Update the config entry data
                new_data = dict(self.config_entry.data)
                new_data[CONF_UUID] = uuid
                if recap_uuid:
                    new_data[CONF_RECAP_UUID] = recap_uuid
                else:
                    new_data.pop(CONF_RECAP_UUID, None)

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                    unique_id=uuid,
                )
                return self.async_create_entry(title="", data={})

        current_uuid = self.config_entry.data.get(CONF_UUID, "")
        current_recap_uuid = self.config_entry.data.get(CONF_RECAP_UUID, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UUID, default=current_uuid): str,
                    vol.Optional(CONF_RECAP_UUID, default=current_recap_uuid): str,
                }
            ),
            errors=errors,
        )


class DateRangeSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding date range configurations."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle user step to add a new date range subentry."""
        if user_input is not None:
            # Use the date range as part of the title
            name = user_input.get(CONF_SUBENTRY_NAME, "").strip()
            date_range = user_input[CONF_DATE_RANGE]

            if not name:
                # Generate a default name based on date range
                name = date_range.replace("_", " ").title()

            return self.async_create_entry(
                title=name,
                data={
                    CONF_DATE_RANGE: date_range,
                    CONF_SUBENTRY_NAME: name,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SUBENTRY_NAME, default=""): str,
                    vol.Required(CONF_DATE_RANGE, default=DEFAULT_DATE_RANGE): vol.In(
                        DATE_RANGE_OPTIONS
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of an existing subentry."""
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            name = user_input.get(CONF_SUBENTRY_NAME, "").strip()
            date_range = user_input[CONF_DATE_RANGE]

            if not name:
                name = date_range.replace("_", " ").title()

            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=name,
                data={
                    CONF_DATE_RANGE: date_range,
                    CONF_SUBENTRY_NAME: name,
                },
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SUBENTRY_NAME,
                        default=subentry.data.get(CONF_SUBENTRY_NAME, ""),
                    ): str,
                    vol.Required(
                        CONF_DATE_RANGE,
                        default=subentry.data.get(CONF_DATE_RANGE, DEFAULT_DATE_RANGE),
                    ): vol.In(DATE_RANGE_OPTIONS),
                }
            ),
        )


class InvalidUUID(Exception):
    """Error to indicate the highlights UUID is invalid."""


class InvalidRecapUUID(Exception):
    """Error to indicate the recap UUID is invalid."""
