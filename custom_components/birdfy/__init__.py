"""The Birdfy integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    BirdfyAccountApi,
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
    CONF_TOKEN,
    CONF_UDID,
    CONF_USER_ID,
    CONF_USERNAME,
    CONF_UUID,
    DEFAULT_DATE_RANGE,
    DOMAIN,
)
from .coordinator import (
    BirdfyHighlightsCoordinator,
    BirdfyMomentsCoordinator,
    BirdfyRecapCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.IMAGE]
CARD_URL_PATH = f"/{DOMAIN}/birdfy-moments-card.js"
CARD_RESOURCE_URL = f"{CARD_URL_PATH}?v=1.0.2"
CARD_FILE_PATH = Path(__file__).parent / "frontend" / "birdfy-moments-card.js"


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Register the custom Birdfy Moments Lovelace card with Home Assistant."""
    if not hass.data[DOMAIN].get("_frontend_registered") and CARD_FILE_PATH.is_file():
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    CARD_URL_PATH,
                    str(CARD_FILE_PATH),
                    cache_headers=False,
                )
            ]
        )
        add_extra_js_url(hass, CARD_RESOURCE_URL)
        hass.data[DOMAIN]["_frontend_registered"] = True
        _LOGGER.debug("Registered Birdfy Moments card static path at %s", CARD_URL_PATH)

    # Also ensure it is registered in Lovelace resources so existing tabs load it immediately
    lovelace = hass.data.get("lovelace")
    resources = (
        getattr(lovelace, "resources", None)
        or (lovelace.get("resources") if isinstance(lovelace, dict) else None)
    )
    if resources is not None and hasattr(resources, "store") and resources.store is not None:
        if not getattr(resources, "loaded", True) and hasattr(resources, "async_load"):
            await resources.async_load()
        for item in resources.async_items():
            item_url = str(item.get("url", ""))
            if "birdfy-moments-card.js" in item_url:
                if item_url != CARD_RESOURCE_URL and hasattr(resources, "async_update_item"):
                    await resources.async_update_item(item["id"], {"url": CARD_RESOURCE_URL})
                return
        if hasattr(resources, "async_create_item"):
            await resources.async_create_item(
                {"res_type": "module", "url": CARD_RESOURCE_URL}
            )
            _LOGGER.info("Added Birdfy Moments card to Lovelace resources: %s", CARD_RESOURCE_URL)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Birdfy from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend_card(hass)

    entry_store: dict[str, Any] = {
        "coordinators": {},
        "recap_coordinator": None,
        "moments_coordinators": {},
        "account_api": None,
        "devices": [],
    }
    hass.data[DOMAIN][entry.entry_id] = entry_store

    session = async_get_clientsession(hass)

    # 1. Set up Highlights coordinators if Highlight UUID is configured
    highlight_uuid = entry.data.get(CONF_UUID, "").strip()
    if highlight_uuid:
        api = BirdfyHighlightsApi(highlight_uuid, session)
        for subentry_id, subentry in entry.subentries.items():
            await _async_setup_highlights_subentry(hass, entry, subentry, api)

        if not entry.subentries:
            coordinator = BirdfyHighlightsCoordinator(
                hass, api, entry, subentry_id=None, date_range=DEFAULT_DATE_RANGE
            )
            await coordinator.async_config_entry_first_refresh()
            entry_store["coordinators"]["default"] = coordinator

    # 2. Set up Recap coordinator if Recap UUID is configured
    recap_uuid = entry.data.get(CONF_RECAP_UUID, "").strip()
    if recap_uuid:
        recap_api = BirdfyRecapApi(recap_uuid, session)
        recap_coordinator = BirdfyRecapCoordinator(hass, recap_api, entry)
        await recap_coordinator.async_config_entry_first_refresh()
        entry_store["recap_coordinator"] = recap_coordinator

    # 3. Set up Moments coordinators if Birdfy Account credentials are configured
    username = entry.data.get(CONF_USERNAME, "").strip()
    password = entry.data.get(CONF_PASSWORD, "")
    token = entry.data.get(CONF_TOKEN, "")
    if (username and password) or token:
        account_api = BirdfyAccountApi(
            session,
            username=username,
            password=password,
            token=token,
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
            user_id=entry.data.get(CONF_USER_ID),
            region=entry.data.get(CONF_REGION),
            udid=entry.data.get(CONF_UDID),
        )
        try:
            devices = await account_api.async_get_devices()
        except BirdfyMomentsApiError as err:
            raise ConfigEntryNotReady(
                f"Failed to fetch Birdfy devices: {err}"
            ) from err

        entry_store["account_api"] = account_api
        entry_store["devices"] = devices

        for subentry_id, subentry in entry.subentries.items():
            await _async_setup_moments_subentry(
                hass, entry, subentry, account_api, devices
            )

        if not entry.subentries:
            default_moments_coords: list[BirdfyMomentsCoordinator] = []
            for device in devices:
                m_coord = BirdfyMomentsCoordinator(
                    hass,
                    account_api,
                    entry,
                    device,
                    subentry_id=None,
                    date_range=DEFAULT_DATE_RANGE,
                )
                await m_coord.async_config_entry_first_refresh()
                default_moments_coords.append(m_coord)
            entry_store["moments_coordinators"]["default"] = default_moments_coords

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register listener for subentry or options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def _async_setup_highlights_subentry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    api: BirdfyHighlightsApi,
) -> None:
    """Set up a Highlights subentry coordinator."""
    date_range = subentry.data.get(CONF_DATE_RANGE, DEFAULT_DATE_RANGE)

    coordinator = BirdfyHighlightsCoordinator(
        hass, api, entry, subentry_id=subentry.subentry_id, date_range=date_range
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinators"][
        subentry.subentry_id
    ] = coordinator


async def _async_setup_moments_subentry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    account_api: BirdfyAccountApi,
    devices: list[dict[str, Any]],
) -> None:
    """Set up Moments subentry coordinators for all discovered devices."""
    date_range = subentry.data.get(CONF_DATE_RANGE, DEFAULT_DATE_RANGE)
    sub_coords: list[BirdfyMomentsCoordinator] = []

    for device in devices:
        m_coord = BirdfyMomentsCoordinator(
            hass,
            account_api,
            entry,
            device,
            subentry_id=subentry.subentry_id,
            date_range=date_range,
        )
        await m_coord.async_config_entry_first_refresh()
        sub_coords.append(m_coord)

    hass.data[DOMAIN][entry.entry_id]["moments_coordinators"][
        subentry.subentry_id
    ] = sub_coords


async def async_setup_subentry(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> bool:
    """Set up a subentry dynamically."""
    session = async_get_clientsession(hass)
    entry_store = hass.data[DOMAIN][entry.entry_id]

    highlight_uuid = entry.data.get(CONF_UUID, "").strip()
    if highlight_uuid:
        api = BirdfyHighlightsApi(highlight_uuid, session)
        await _async_setup_highlights_subentry(hass, entry, subentry, api)

    account_api = entry_store.get("account_api")
    devices = entry_store.get("devices", [])
    if account_api and devices:
        await _async_setup_moments_subentry(
            hass, entry, subentry, account_api, devices
        )

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
        entry_store = hass.data[DOMAIN][entry.entry_id]
        entry_store["coordinators"].pop(subentry.subentry_id, None)
        entry_store["moments_coordinators"].pop(subentry.subentry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
