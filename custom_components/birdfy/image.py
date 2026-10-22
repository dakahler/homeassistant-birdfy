"""Image platform for Birdfy."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BirdfyHighlightsCoordinator, BirdfyMomentsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    subentry_id: str | None = None,
) -> None:
    """Set up Birdfy image entities."""
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    moments_coordinators = hass.data[DOMAIN][entry.entry_id].get("moments_coordinators", {})

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

        for m_coord in moments_coordinators.get(subentry_id, []):
            subentry = entry.subentries.get(subentry_id)
            subentry_name = subentry.title if subentry else "Unknown"
            entities.append(
                BirdfyLastMomentImage(
                    hass, m_coord, entry, subentry_id, subentry_name
                )
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

        # Create images for all Moments coordinators
        for coord_id, m_coord_list in moments_coordinators.items():
            if coord_id == "default":
                for m_coord in m_coord_list:
                    entities.append(
                        BirdfyLastMomentImage(hass, m_coord, entry, None, None)
                    )
            else:
                subentry = entry.subentries.get(coord_id)
                subentry_name = subentry.title if subentry else "Unknown"
                for m_coord in m_coord_list:
                    entities.append(
                        BirdfyLastMomentImage(
                            hass, m_coord, entry, coord_id, subentry_name
                        )
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

        thumbnails = self.coordinator.data.get("thumbnails", {})
        _LOGGER.debug("Available thumbnails: %s", list(thumbnails.keys()))

        if not thumbnails:
            _LOGGER.debug("No thumbnails available")
            return None

        highlights = self.coordinator.data.get("highlights", [])

        # Try to get thumbnail for the most recent highlight species
        if highlights:
            last_highlight = highlights[0]
            species = last_highlight.get("species")
            _LOGGER.debug("Last highlight species: %s", species)

            if species and species in thumbnails:
                url = thumbnails[species]
                _LOGGER.debug("Thumbnail URL for %s: %s", species, url)
                return url
            else:
                _LOGGER.debug("Species '%s' not in thumbnails, checking highlights for match", species)

            # Try to find a highlight species that has a thumbnail
            for highlight in highlights:
                h_species = highlight.get("species")
                if h_species and h_species in thumbnails:
                    url = thumbnails[h_species]
                    _LOGGER.debug("Found thumbnail for highlight species %s: %s", h_species, url)
                    return url

        # Fallback: use first available thumbnail
        if thumbnails:
            first_species = next(iter(thumbnails))
            url = thumbnails[first_species]
            _LOGGER.debug("Fallback to first thumbnail (%s): %s", first_species, url)
            return url

        return None

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


class BirdfyLastMomentImage(CoordinatorEntity, ImageEntity):
    """Image entity showing the snapshot of the most recent Moment."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: BirdfyMomentsCoordinator,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        subentry_name: str | None = None,
    ) -> None:
        """Initialize the Moments image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)

        self._subentry_id = subentry_id
        self._subentry_name = subentry_name
        self._last_url: str | None = None
        self._last_alarm_id: Any = None
        self._cached_image: bytes | None = None
        self._attr_image_last_updated = datetime.now()

        sn = coordinator.serial_number

        if subentry_name:
            self._attr_name = f"Last Moment - {subentry_name}"
        else:
            self._attr_name = "Last Moment"

        if subentry_id:
            self._attr_unique_id = (
                f"{entry.entry_id}_moments_{sn}_{subentry_id}_last_moment_image"
            )
            device_id = f"{entry.entry_id}_moments_{sn}_{subentry_id}"
            device_name = f"Birdfy Moments - {coordinator.device_name} ({subentry_name})"
        else:
            self._attr_unique_id = (
                f"{entry.entry_id}_moments_{sn}_last_moment_image"
            )
            device_id = f"{entry.entry_id}_moments_{sn}"
            device_name = f"Birdfy Moments - {coordinator.device_name}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Birdfy",
            "model": coordinator.device_info_raw.get("productCode") or "Moments API",
            "serial_number": sn,
        }

    def _get_moment_with_image(self) -> dict[str, Any] | None:
        """Return the most recent moment that has an image URL."""
        if self.coordinator.data is None:
            return None

        for moment in self.coordinator.data.get("moments", []):
            if moment.get("image_url"):
                return moment

        return self.coordinator.data.get("last_moment")

    def _get_image_url(self) -> str | None:
        """Get the current snapshot image URL from coordinator data."""
        moment = self._get_moment_with_image()
        return moment.get("image_url") if moment else None

    async def async_image(self) -> bytes | None:
        """Return bytes of the latest Moment snapshot."""
        url = self._get_image_url()
        if url is None:
            return None

        if url == self._last_url and self._cached_image is not None:
            return self._cached_image

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    self._cached_image = await response.read()
                    self._last_url = url
                    return self._cached_image
                _LOGGER.warning(
                    "Failed to fetch Moment snapshot image, status: %s",
                    response.status,
                )
        except Exception as err:
            _LOGGER.exception("Error fetching Moment snapshot image: %s", err)

        return self._cached_image

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the Moments coordinator."""
        moment = self._get_moment_with_image()
        new_url = moment.get("image_url") if moment else None
        new_alarm_id = moment.get("alarm_id") if moment else None

        if new_url != self._last_url or (
            new_alarm_id is not None and new_alarm_id != self._last_alarm_id
        ):
            self._cached_image = None
            self._last_alarm_id = new_alarm_id
            self._attr_image_last_updated = datetime.now()

        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for the latest Moment snapshot."""
        moment = self._get_moment_with_image()
        if not moment:
            return {}

        attrs: dict[str, Any] = {
            "alarm_id": moment.get("alarm_id"),
            "species": moment.get("species"),
            "ai_labels": moment.get("ai_labels", []),
            "image_url": moment.get("image_url"),
        }

        if moment.get("time"):
            attrs["detection_time"] = datetime.fromtimestamp(
                moment["time"] / 1000
            ).isoformat()

        if moment.get("video_url"):
            attrs["video_url"] = moment.get("video_url")

        return attrs
