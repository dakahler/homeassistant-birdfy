"""The Birdfy integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BirdfyHighlightsApi, BirdfyRecapApi
from .const import DOMAIN, CONF_UUID, CONF_RECAP_UUID, CONF_DATE_RANGE, DEFAULT_DATE_RANGE
from .coordinator import BirdfyHighlightsCoordinator, BirdfyRecapCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.IMAGE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Birdfy from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinators": {}, "recap_coordinator": None}

    session = async_get_clientsession(hass)
    api = BirdfyHighlightsApi(entry.data[CONF_UUID], session)

    # Set up coordinators for each subentry
    for subentry_id, subentry in entry.subentries.items():
        await _async_setup_subentry(hass, entry, subentry, api)

    # If no subentries exist, create a default coordinator with "today" date range
    if not entry.subentries:
        coordinator = BirdfyHighlightsCoordinator(
            hass, api, entry, subentry_id=None, date_range=DEFAULT_DATE_RANGE
        )
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id]["coordinators"]["default"] = coordinator

    # Set up recap coordinator if recap UUID is provided
    recap_uuid = entry.data.get(CONF_RECAP_UUID)
    if recap_uuid:
        recap_api = BirdfyRecapApi(recap_uuid, session)
        recap_coordinator = BirdfyRecapCoordinator(hass, recap_api, entry)
        await recap_coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id]["recap_coordinator"] = recap_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register listener for subentry changes
    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )

    return True


async def _async_setup_subentry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    api: BirdfyHighlightsApi,
) -> None:
    """Set up a subentry coordinator."""
    date_range = subentry.data.get(CONF_DATE_RANGE, DEFAULT_DATE_RANGE)

    coordinator = BirdfyHighlightsCoordinator(
        hass, api, entry, subentry_id=subentry.subentry_id, date_range=date_range
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinators"][subentry.subentry_id] = coordinator


async def async_setup_subentry(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> bool:
    """Set up a subentry."""
    session = async_get_clientsession(hass)
    api = BirdfyHighlightsApi(entry.data[CONF_UUID], session)

    await _async_setup_subentry(hass, entry, subentry, api)

    # Forward to platforms for this subentry
    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORMS, subentry_id=subentry.subentry_id
    )

    return True


async def async_unload_subentry(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> bool:
    """Unload a subentry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS, subentry_id=subentry.subentry_id
    )

    if unload_ok:
        hass.data[DOMAIN][entry.entry_id]["coordinators"].pop(
            subentry.subentry_id, None
        )

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
