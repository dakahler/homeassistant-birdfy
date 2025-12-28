"""Image platform for Birdfy."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BirdfyHighlightsCoordinator


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
                BirdfyLastBirdImage(coordinator, entry, subentry_id, subentry_name)
            )
    else:
        # Initial setup - create images for all coordinators
        for coord_id, coordinator in coordinators.items():
            if coord_id == "default":
                entities.append(
                    BirdfyLastBirdImage(coordinator, entry, None, None)
                )
            else:
                subentry = entry.subentries.get(coord_id)
                subentry_name = subentry.title if subentry else "Unknown"
                entities.append(
                    BirdfyLastBirdImage(coordinator, entry, coord_id, subentry_name)
                )

    async_add_entities(entities)


class BirdfyLastBirdImage(CoordinatorEntity, ImageEntity):
    """Image entity showing the last bird seen."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        subentry_name: str | None = None,
    ) -> None:
        """Initialize the image entity."""
        super().__init__(coordinator)
        self._subentry_id = subentry_id
        self._subentry_name = subentry_name
        self._cached_url: str | None = None

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

    @property
    def image_url(self) -> str | None:
        """Return the URL of the last bird thumbnail."""
        if self.coordinator.data is None:
            return None

        highlights = self.coordinator.data.get("highlights", [])
        if not highlights:
            return None

        # Get the most recent highlight
        last_highlight = highlights[0]
        species = last_highlight.get("species")

        if not species:
            return None

        # Get thumbnail URL from thumbnails dict
        thumbnails = self.coordinator.data.get("thumbnails", {})
        return thumbnails.get(species)

    @property
    def image_last_updated(self) -> datetime | None:
        """Return the timestamp of when the image was last updated."""
        if self.coordinator.data is None:
            return None

        highlights = self.coordinator.data.get("highlights", [])
        if not highlights:
            return None

        last_time = highlights[0].get("time")
        if last_time:
            return datetime.fromtimestamp(last_time / 1000)

        return None

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
        }

        if last.get("time"):
            attrs["detection_time"] = datetime.fromtimestamp(
                last["time"] / 1000
            ).isoformat()

        if last.get("video_url"):
            attrs["video_url"] = last.get("video_url")

        return attrs
