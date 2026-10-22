"""Config flow for Birdfy integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    BirdfyAccountApi,
    BirdfyAuthError,
    BirdfyHighlightsApi,
    BirdfyMomentsApiError,
    BirdfyRecapApi,
)
from .const import (
    CONF_DATE_RANGE,
    CONF_PASSWORD,
    CONF_RECAP_UUID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SUBENTRY_NAME,
    CONF_TOKEN,
    CONF_UDID,
    CONF_USER_ID,
    CONF_USERNAME,
    CONF_UUID,
    DATE_RANGE_OPTIONS,
    DEFAULT_DATE_RANGE,
    DOMAIN,
    SUBENTRY_TYPE_DATE_RANGE,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_USERNAME, default=""): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
        vol.Optional(CONF_UUID, default=""): str,
        vol.Optional(CONF_RECAP_UUID, default=""): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    username = data.get(CONF_USERNAME, "").strip()
    password = data.get(CONF_PASSWORD, "")
    uuid = data.get(CONF_UUID, "").strip()
    recap_uuid = data.get(CONF_RECAP_UUID, "").strip()

    if not username and not password and not uuid and not recap_uuid:
        raise MissingConfiguration

    if bool(username) != bool(password):
        raise InvalidAuth

    entry_data: dict[str, Any] = {}

    # Validate Birdfy account login if provided
    if username and password:
        account_api = BirdfyAccountApi(
            session,
            username=username,
            password=password,
            udid=data.get(CONF_UDID),
        )
        try:
            await account_api.async_login(username, password)
        except (BirdfyAuthError, BirdfyMomentsApiError) as err:
            raise InvalidAuth from err

        entry_data[CONF_USERNAME] = username
        entry_data[CONF_PASSWORD] = password
        entry_data[CONF_TOKEN] = account_api.token
        entry_data[CONF_REFRESH_TOKEN] = account_api.refresh_token
        entry_data[CONF_USER_ID] = account_api.user_id
        entry_data[CONF_REGION] = account_api.region
        entry_data[CONF_UDID] = account_api.udid

    # Validate highlights UUID if provided
    if uuid:
        api = BirdfyHighlightsApi(uuid, session)
        if not await api.async_validate_uuid():
            raise InvalidUUID
        entry_data[CONF_UUID] = uuid

    # Validate recap UUID if provided
    if recap_uuid:
        recap_api = BirdfyRecapApi(recap_uuid, session)
        if not await recap_api.async_validate_uuid():
            raise InvalidRecapUUID
        entry_data[CONF_RECAP_UUID] = recap_uuid

    if username:
        title = f"Birdfy ({username})"
        unique_id = str(entry_data.get(CONF_USER_ID) or username)
    elif uuid:
        title = f"Birdfy ({uuid[:8]}...)"
        unique_id = uuid
    else:
        title = f"Birdfy Recap ({recap_uuid[:8]}...)"
        unique_id = f"recap_{recap_uuid}"

    return {"title": title, "unique_id": unique_id, "data": entry_data}


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
            except MissingConfiguration:
                errors["base"] = "missing_configuration"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidUUID:
                errors["base"] = "invalid_uuid"
            except InvalidRecapUUID:
                errors["base"] = "invalid_recap_uuid"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"], data=info["data"]
                )

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
    """Handle options flow to update Birdfy account credentials and UUIDs."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            merged = dict(self.config_entry.data)
            merged.update(user_input)
            try:
                info = await validate_input(self.hass, merged)
            except MissingConfiguration:
                errors["base"] = "missing_configuration"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidUUID:
                errors["base"] = "invalid_uuid"
            except InvalidRecapUUID:
                errors["base"] = "invalid_recap_uuid"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception in options flow")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=info["data"]
                )
                return self.async_create_entry(title="", data={})

        current_username = self.config_entry.data.get(CONF_USERNAME, "")
        current_password = self.config_entry.data.get(CONF_PASSWORD, "")
        current_uuid = self.config_entry.data.get(CONF_UUID, "")
        current_recap_uuid = self.config_entry.data.get(CONF_RECAP_UUID, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME, default=current_username): str,
                    vol.Optional(CONF_PASSWORD, default=current_password): str,
                    vol.Optional(CONF_UUID, default=current_uuid): str,
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


class MissingConfiguration(Exception):
    """Error to indicate neither account credentials nor UUIDs were provided."""


class InvalidAuth(Exception):
    """Error to indicate Birdfy account credentials are invalid."""


class InvalidUUID(Exception):
    """Error to indicate the highlights UUID is invalid."""


class InvalidRecapUUID(Exception):
    """Error to indicate the recap UUID is invalid."""
