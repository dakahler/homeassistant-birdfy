"""Sensor platform for Birdfy."""

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
    ATTR_DATE_RANGE,
    ATTR_START_TIME,
    ATTR_END_TIME,
    ATTR_RECAP_DATE,
    ATTR_RECAP_DURATION,
    ATTR_RECAP_SPECIES_SURPASSES,
    ATTR_RECAP_VISITS_SURPASSES,
    ATTR_RECAP_TOP_BIRD,
    ATTR_RECAP_UNCOMMON_BIRD,
    ATTR_RECAP_UNCOMMON_SURPASSES,
    ATTR_RECAP_VIDEO_HIGHLIGHTS,
    ATTR_RECAP_VIDEO_TOP_BIRD,
    ATTR_RECAP_VIDEO_UNCOMMON,
    ATTR_RECAP_VIDEO_BUSIEST,
    ATTR_RECAP_VIDEO_HUMMINGBIRD,
)
from .coordinator import BirdfyHighlightsCoordinator, BirdfyRecapCoordinator


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

RECAP_SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="recap_species_count",
        name="Monthly Species Count",
        icon="mdi:bird",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="species",
    ),
    SensorEntityDescription(
        key="recap_bird_visits",
        name="Monthly Bird Visits",
        icon="mdi:bird",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="visits",
    ),
    SensorEntityDescription(
        key="recap_event_count",
        name="Monthly Events",
        icon="mdi:calendar-check",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="events",
    ),
    SensorEntityDescription(
        key="recap_top_bird",
        name="Monthly Top Bird",
        icon="mdi:trophy",
    ),
    SensorEntityDescription(
        key="recap_uncommon_bird",
        name="Monthly Uncommon Bird",
        icon="mdi:star",
    ),
    SensorEntityDescription(
        key="recap_hummingbird_species",
        name="Monthly Hummingbird Species",
        icon="mdi:bird",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="species",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    subentry_id: str | None = None,
) -> None:
    """Set up Birdfy sensors."""
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    recap_coordinator = hass.data[DOMAIN][entry.entry_id].get("recap_coordinator")

    entities = []

    if subentry_id:
        # Set up sensors for a specific subentry
        coordinator = coordinators.get(subentry_id)
        if coordinator:
            subentry = entry.subentries.get(subentry_id)
            subentry_name = subentry.title if subentry else "Unknown"
            entities.extend(
                _create_sensors_for_coordinator(
                    coordinator, entry, subentry_id, subentry_name
                )
            )
    else:
        # Initial setup - create sensors for all coordinators
        for coord_id, coordinator in coordinators.items():
            if coord_id == "default":
                # Default coordinator (no subentries)
                entities.extend(
                    _create_sensors_for_coordinator(coordinator, entry, None, None)
                )
            else:
                # Subentry coordinator
                subentry = entry.subentries.get(coord_id)
                subentry_name = subentry.title if subentry else "Unknown"
                entities.extend(
                    _create_sensors_for_coordinator(
                        coordinator, entry, coord_id, subentry_name
                    )
                )

        # Add recap sensors if recap coordinator exists (only on initial setup)
        if recap_coordinator:
            entities.extend(_create_recap_sensors(recap_coordinator, entry))

    async_add_entities(entities)


def _create_sensors_for_coordinator(
    coordinator: BirdfyHighlightsCoordinator,
    entry: ConfigEntry,
    subentry_id: str | None,
    subentry_name: str | None,
) -> list[SensorEntity]:
    """Create sensor entities for a coordinator."""
    entities = []

    for description in SENSOR_DESCRIPTIONS:
        entities.append(
            BirdfyHighlightsSensor(
                coordinator, entry, description, subentry_id, subentry_name
            )
        )

    # Add the species list sensor
    entities.append(
        BirdfySpeciesListSensor(coordinator, entry, subentry_id, subentry_name)
    )

    return entities


class BirdfyHighlightsSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Birdfy sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        subentry_id: str | None = None,
        subentry_name: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._subentry_id = subentry_id
        self._subentry_name = subentry_name

        # Create unique ID based on subentry
        if subentry_id:
            self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_{description.key}"
        else:
            self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Create device info - each subentry gets its own device
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
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(
        self,
        coordinator: BirdfyHighlightsCoordinator,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        subentry_name: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._subentry_id = subentry_id
        self._subentry_name = subentry_name

        # Set name based on subentry
        if subentry_name:
            self._attr_name = f"Bird Species - {subentry_name}"
        else:
            self._attr_name = "Bird Species"

        # Create unique ID based on subentry
        if subentry_id:
            self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_species_list"
        else:
            self._attr_unique_id = f"{entry.entry_id}_species_list"

        # Create device info - each subentry gets its own device
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
            ATTR_DATE_RANGE: data.get("date_range"),
        }

        # Add timestamps if available
        start_time = data.get("start_time")
        if start_time:
            attrs[ATTR_START_TIME] = datetime.fromtimestamp(
                start_time / 1000
            ).isoformat()

        end_time = data.get("end_time")
        if end_time:
            attrs[ATTR_END_TIME] = datetime.fromtimestamp(
                end_time / 1000
            ).isoformat()

        last_detection = data.get("last_detection")
        if last_detection:
            attrs[ATTR_LAST_DETECTION] = datetime.fromtimestamp(
                last_detection / 1000
            ).isoformat()

        return attrs


def _create_recap_sensors(
    coordinator: BirdfyRecapCoordinator,
    entry: ConfigEntry,
) -> list[SensorEntity]:
    """Create recap sensor entities."""
    entities = []

    for description in RECAP_SENSOR_DESCRIPTIONS:
        entities.append(BirdfyRecapSensor(coordinator, entry, description))

    # Add the monthly recap summary sensor
    entities.append(BirdfyRecapSummarySensor(coordinator, entry))

    return entities


class BirdfyRecapSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Birdfy monthly recap sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BirdfyRecapCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        self._attr_unique_id = f"{entry.entry_id}_recap_{description.key}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_recap")},
            "name": "Birdfy Monthly Recap",
            "manufacturer": "Birdfy",
            "model": "Recap API",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key

        if key == "recap_species_count":
            return self.coordinator.data.get("bird_species_count", 0)
        elif key == "recap_bird_visits":
            return self.coordinator.data.get("bird_visits", 0)
        elif key == "recap_event_count":
            return self.coordinator.data.get("event_count", 0)
        elif key == "recap_top_bird":
            return self.coordinator.data.get("top_bird")
        elif key == "recap_uncommon_bird":
            return self.coordinator.data.get("uncommon_bird")
        elif key == "recap_hummingbird_species":
            return self.coordinator.data.get("hummingbird_species_count", 0)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        key = self.entity_description.key
        attrs = {}

        if key == "recap_species_count":
            surpass = self.coordinator.data.get("species_surpasses_percent")
            if surpass is not None:
                attrs[ATTR_RECAP_SPECIES_SURPASSES] = surpass

        elif key == "recap_bird_visits":
            surpass = self.coordinator.data.get("visits_surpasses_percent")
            if surpass is not None:
                attrs[ATTR_RECAP_VISITS_SURPASSES] = surpass

        elif key == "recap_top_bird":
            video = self.coordinator.data.get("video_top_bird")
            if video:
                attrs[ATTR_RECAP_VIDEO_TOP_BIRD] = video

        elif key == "recap_uncommon_bird":
            surpass = self.coordinator.data.get("uncommon_surpasses_percent")
            if surpass is not None:
                attrs[ATTR_RECAP_UNCOMMON_SURPASSES] = surpass
            video = self.coordinator.data.get("video_uncommon")
            if video:
                attrs[ATTR_RECAP_VIDEO_UNCOMMON] = video

        elif key == "recap_hummingbird_species":
            visits = self.coordinator.data.get("hummingbird_visits", 0)
            attrs["hummingbird_visits"] = visits
            video = self.coordinator.data.get("video_hummingbird")
            if video:
                attrs[ATTR_RECAP_VIDEO_HUMMINGBIRD] = video

        return attrs


class BirdfyRecapSummarySensor(CoordinatorEntity, SensorEntity):
    """Sensor that exposes the full monthly recap data."""

    _attr_has_entity_name = True
    _attr_name = "Monthly Recap"
    _attr_icon = "mdi:calendar-month"

    def __init__(
        self,
        coordinator: BirdfyRecapCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_recap_summary"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_recap")},
            "name": "Birdfy Monthly Recap",
            "manufacturer": "Birdfy",
            "model": "Recap API",
        }

    @property
    def native_value(self) -> str | None:
        """Return the statistics date as state."""
        if self.coordinator.data is None:
            return None

        return self.coordinator.data.get("statistics_date")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all recap data as attributes."""
        if self.coordinator.data is None:
            return {}

        data = self.coordinator.data

        attrs = {
            ATTR_RECAP_DATE: data.get("statistics_date"),
            ATTR_RECAP_DURATION: data.get("duration"),
            "event_count": data.get("event_count", 0),
            "bird_species_count": data.get("bird_species_count", 0),
            "bird_visits": data.get("bird_visits", 0),
            ATTR_RECAP_SPECIES_SURPASSES: data.get("species_surpasses_percent"),
            ATTR_RECAP_VISITS_SURPASSES: data.get("visits_surpasses_percent"),
            ATTR_RECAP_TOP_BIRD: data.get("top_bird"),
            ATTR_RECAP_UNCOMMON_BIRD: data.get("uncommon_bird"),
            ATTR_RECAP_UNCOMMON_SURPASSES: data.get("uncommon_surpasses_percent"),
            "hummingbird_species_count": data.get("hummingbird_species_count", 0),
            "hummingbird_visits": data.get("hummingbird_visits", 0),
            ATTR_RECAP_VIDEO_HIGHLIGHTS: data.get("video_highlights"),
            ATTR_RECAP_VIDEO_TOP_BIRD: data.get("video_top_bird"),
            ATTR_RECAP_VIDEO_UNCOMMON: data.get("video_uncommon"),
            ATTR_RECAP_VIDEO_BUSIEST: data.get("video_busiest"),
            ATTR_RECAP_VIDEO_HUMMINGBIRD: data.get("video_hummingbird"),
        }

        return attrs
