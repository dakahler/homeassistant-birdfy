"""Image platform for Birdfy."""

from __future__ import annotations

from datetime import datetime
import logging

import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BirdfyHighlightsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    subentry_id: str | None = None,
) -> None:
    """Set up Birdfy image entities."""
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    entities = []

    if subentry_id:
        # Set up image for a specific subentry
        coordinator = coordinators.get(subentry_id)
        if coordinator:
            subentry = entry.subentries.get(subentry_id)
            subentry_name = subentry.title if subentry else "Unknown"
            entities.append(
                BirdfyLastBirdImage(hass, coordinator, entry, subentry_id, subentry_name)
            )
    else:
        # Initial setup - create images for all coordinators
        for coord_id, coordinator in coordinators.items():
            if coord_id == "default":
                entities.append(
                    BirdfyLastBirdImage(hass, coordinator, entry, None, None)
                )
            else:
                subentry = entry.subentries.get(coord_id)
                subentry_name = subentry.title if subentry else "Unknown"
                entities.append(
                    BirdfyLastBirdImage(hass, coordinator, entry, coord_id, subentry_name)
                )

    _LOGGER.debug("Setting up %d image entities", len(entities))
    async_add_entities(entities)


class BirdfyLastBirdImage(CoordinatorEntity, ImageEntity):
    """Image entity showing the last bird seen."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        subentry_name: str | None = None,
    ) -> None:
        """Initialize the image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)

        self._subentry_id = subentry_id
        self._subentry_name = subentry_name
        self._last_url: str | None = None
        self._cached_image: bytes | None = None
        self._attr_image_last_updated = datetime.now()

        # Set name based on subentry
        if subentry_name:
            self._attr_name = f"Last Bird - {subentry_name}"
        else:
            self._attr_name = "Last Bird"

        # Create unique ID based on subentry
        if subentry_id:
            self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_last_bird_image"
        else:
            self._attr_unique_id = f"{entry.entry_id}_last_bird_image"

        # Create device info
        if subentry_id and subentry_name:
            device_id = f"{entry.entry_id}_{subentry_id}"
            device_name = f"Birdfy - {subentry_name}"
        else:
            device_id = entry.entry_id
            device_name = "Birdfy"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Birdfy",
            "model": "Highlights API",
        }

        _LOGGER.debug("Initialized BirdfyLastBirdImage entity: %s", self._attr_unique_id)

    def _get_image_url(self) -> str | None:
        """Get the current image URL from coordinator data."""
        if self.coordinator.data is None:
            _LOGGER.debug("No coordinator data available")
            return None

        highlights = self.coordinator.data.get("highlights", [])
        if not highlights:
            _LOGGER.debug("No highlights in data")
            return None

        # Get the most recent highlight
        last_highlight = highlights[0]
        species = last_highlight.get("species")
        _LOGGER.debug("Last highlight species: %s", species)

        if not species:
            _LOGGER.debug("No species in last highlight")
            return None

        # Get thumbnail URL from thumbnails dict
        thumbnails = self.coordinator.data.get("thumbnails", {})
        url = thumbnails.get(species)
        _LOGGER.debug("Thumbnail URL for %s: %s", species, url)
        return url

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""
        url = self._get_image_url()
        _LOGGER.debug("async_image called, URL: %s", url)

        if url is None:
            _LOGGER.debug("No image URL available")
            return None

        # Return cached image if URL hasn't changed
        if url == self._last_url and self._cached_image is not None:
            _LOGGER.debug("Returning cached image")
            return self._cached_image

        # Fetch new image
        _LOGGER.debug("Fetching new image from: %s", url)
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                _LOGGER.debug("Image fetch response status: %s", response.status)
                if response.status == 200:
                    self._cached_image = await response.read()
                    self._last_url = url
                    _LOGGER.debug("Successfully fetched image, size: %d bytes", len(self._cached_image))
                    return self._cached_image
                else:
                    _LOGGER.warning("Failed to fetch image, status: %s", response.status)
        except Exception as err:
            _LOGGER.exception("Error fetching image: %s", err)

        return self._cached_image

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if image URL changed to update the timestamp
        new_url = self._get_image_url()
        if new_url != self._last_url:
            _LOGGER.debug("Image URL changed from %s to %s", self._last_url, new_url)
            self._cached_image = None  # Clear cache
            self._attr_image_last_updated = datetime.now()

        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        highlights = self.coordinator.data.get("highlights", [])
        if not highlights:
            return {}

        last = highlights[0]
        attrs = {
            "species": last.get("species"),
            "title": last.get("title"),
            "category": last.get("category"),
            "image_url": self._get_image_url(),
        }

        if last.get("time"):
            attrs["detection_time"] = datetime.fromtimestamp(
                last["time"] / 1000
            ).isoformat()

        if last.get("video_url"):
            attrs["video_url"] = last.get("video_url")

        return attrs
