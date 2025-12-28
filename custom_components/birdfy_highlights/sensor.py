"""Sensor platform for Birdfy Highlights."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_SPECIES_COUNT,
    ATTR_SPECIES_LIST,
    ATTR_HIGHLIGHTS,
    ATTR_NEW_SPECIES,
    ATTR_LAST_DETECTION,
    ATTR_THUMBNAILS,
)
from .coordinator import BirdfyHighlightsCoordinator


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="species_count",
        name="Bird Species Count",
        icon="mdi:bird",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="species",
    ),
    SensorEntityDescription(
        key="last_species",
        name="Last Bird Species",
        icon="mdi:bird",
    ),
    SensorEntityDescription(
        key="new_species_count",
        name="New Species Today",
        icon="mdi:bird",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="species",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Birdfy Highlights sensors."""
    coordinator: BirdfyHighlightsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for description in SENSOR_DESCRIPTIONS:
        entities.append(BirdfyHighlightsSensor(coordinator, entry, description))

    # Add the species list sensor
    entities.append(BirdfySpeciesListSensor(coordinator, entry))

    async_add_entities(entities)


class BirdfyHighlightsSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Birdfy Highlights sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Birdfy Highlights",
            "manufacturer": "Birdfy",
            "model": "Highlights API",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key

        if key == "species_count":
            return self.coordinator.data.get("species_count", 0)
        elif key == "last_species":
            highlights = self.coordinator.data.get("highlights", [])
            if highlights:
                return highlights[0].get("species")
            return None
        elif key == "new_species_count":
            return len(self.coordinator.data.get("new_species", []))

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        key = self.entity_description.key
        attrs = {}

        if key == "species_count":
            attrs[ATTR_SPECIES_LIST] = self.coordinator.data.get("species_list", [])
            attrs[ATTR_THUMBNAILS] = self.coordinator.data.get("thumbnails", {})

        elif key == "last_species":
            highlights = self.coordinator.data.get("highlights", [])
            if highlights:
                last = highlights[0]
                attrs["title"] = last.get("title")
                attrs["category"] = last.get("category")
                attrs["video_url"] = last.get("video_url")
                if last.get("time"):
                    attrs["detection_time"] = datetime.fromtimestamp(
                        last["time"] / 1000
                    ).isoformat()

        elif key == "new_species_count":
            attrs[ATTR_NEW_SPECIES] = self.coordinator.data.get("new_species", [])

        return attrs


class BirdfySpeciesListSensor(CoordinatorEntity, SensorEntity):
    """Sensor that exposes the full species list and highlights."""

    _attr_has_entity_name = True
    _attr_name = "Bird Species Today"
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(
        self,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_species_today"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Birdfy Highlights",
            "manufacturer": "Birdfy",
            "model": "Highlights API",
        }

    @property
    def native_value(self) -> str | None:
        """Return comma-separated list of species."""
        if self.coordinator.data is None:
            return None

        species = self.coordinator.data.get("species_list", [])
        return ", ".join(species) if species else "No birds today"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all highlights data as attributes."""
        if self.coordinator.data is None:
            return {}

        data = self.coordinator.data

        attrs = {
            ATTR_SPECIES_COUNT: data.get("species_count", 0),
            ATTR_SPECIES_LIST: data.get("species_list", []),
            ATTR_NEW_SPECIES: data.get("new_species", []),
            ATTR_THUMBNAILS: data.get("thumbnails", {}),
            ATTR_HIGHLIGHTS: data.get("highlights", []),
        }

        last_detection = data.get("last_detection")
        if last_detection:
            attrs[ATTR_LAST_DETECTION] = datetime.fromtimestamp(
                last_detection / 1000
            ).isoformat()

        return attrs
