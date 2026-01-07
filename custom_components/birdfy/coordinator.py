"""DataUpdateCoordinator for Birdfy."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BirdfyHighlightsApi,
    BirdfyHighlightsApiError,
    BirdfyRecapApi,
    BirdfyRecapApiError,
    get_date_range_timestamps,
)
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, RECAP_SCAN_INTERVAL, DEFAULT_DATE_RANGE

_LOGGER = logging.getLogger(__name__)


class BirdfyHighlightsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Birdfy highlights data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: BirdfyHighlightsApi,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        date_range: str = DEFAULT_DATE_RANGE,
    ) -> None:
        """Initialize the coordinator."""
        name = f"{DOMAIN}_{subentry_id}" if subentry_id else DOMAIN
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.entry = entry
        self.subentry_id = subentry_id
        self._date_range = date_range

    @property
    def date_range(self) -> str:
        """Get the configured date range."""
        return self._date_range

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        try:
            date_range = self.date_range
            data = await self.api.async_get_for_date_range(date_range)

            # Get the actual timestamps used
            start_time, end_time = get_date_range_timestamps(date_range)

            # Process the data
            bird_list = data.get("birdList", [])
            data_list = data.get("dataList", [])

            # Extract species names
            species = [bird.get("name") for bird in bird_list if bird.get("name")]

            # Extract new species from highlights
            new_species = [
                item.get("detectObject")
                for item in data_list
                if item.get("category") == "newBird" and item.get("detectObject")
            ]

            # Get last detection time
            last_detection = None
            if data_list:
                latest = max(data_list, key=lambda x: x.get("createTime", 0))
                last_detection = latest.get("createTime")

            # Build thumbnails dict
            thumbnails = {
                bird.get("name"): bird.get("coverKey")
                for bird in bird_list
                if bird.get("name") and bird.get("coverKey")
            }

            # Build highlights list
            highlights = [
                {
                    "species": item.get("detectObject"),
                    "title": item.get("title"),
                    "category": item.get("category"),
                    "time": item.get("createTime"),
                    "video_url": item.get("fileUrl"),
                }
                for item in data_list
            ]

            return {
                "species_count": len(species),
                "species_list": species,
                "new_species": new_species,
                "last_detection": last_detection,
                "thumbnails": thumbnails,
                "highlights": highlights,
                "date_range": date_range,
                "start_time": start_time,
                "end_time": end_time,
                "raw": data,
            }

        except BirdfyHighlightsApiError as err:
            raise UpdateFailed(f"Error fetching data: {err}")


class BirdfyRecapCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Birdfy monthly recap data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: BirdfyRecapApi,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_recap",
            update_interval=timedelta(minutes=RECAP_SCAN_INTERVAL),
        )
        self.api = api
        self.entry = entry

    async def _async_update_data(self) -> dict:
        """Fetch recap data from API."""
        try:
            data = await self.api.async_get_recap()

            # Process and return the recap data
            return {
                "statistics_date": data.get("statisticsDate"),
                "duration": data.get("duration"),
                "event_count": data.get("eventCount", 0),
                "bird_species_count": data.get("birdSpeciesCount", 0),
                "bird_visits": data.get("birdSpeciesComeCount", 0),
                "species_surpasses_percent": data.get("birdSpeciesCountSurpasses"),
                "visits_surpasses_percent": data.get("birdSpeciesComeCountSurpasses"),
                "top_bird": data.get("maxComeBirdName"),
                "uncommon_bird": data.get("unCommonBirdName"),
                "uncommon_surpasses_percent": data.get("unCommonBirdSurpass"),
                "hummingbird_species_count": data.get("hummingBirdSpeciesCount", 0),
                "hummingbird_visits": data.get("hummingBirdSpeciesComeCount", 0),
                "video_highlights": data.get("collectionMergeFile"),
                "video_top_bird": data.get("maxComeBirdFile"),
                "video_uncommon": data.get("unCommonBirdFile"),
                "video_busiest": data.get("mostBirdNumberFile"),
                "video_hummingbird": data.get("hummingBirdMergeFile"),
                "raw": data,
            }

        except BirdfyRecapApiError as err:
            raise UpdateFailed(f"Error fetching recap data: {err}")
