"""DataUpdateCoordinator for Birdfy Highlights."""

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BirdfyHighlightsApi, BirdfyHighlightsApiError
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class BirdfyHighlightsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Birdfy Highlights data."""

    def __init__(self, hass: HomeAssistant, api: BirdfyHighlightsApi) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        try:
            data = await self.api.async_get_today()

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
                "raw": data,
            }

        except BirdfyHighlightsApiError as err:
            raise UpdateFailed(f"Error fetching data: {err}")
