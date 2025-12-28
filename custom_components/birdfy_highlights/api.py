"""API client for Birdfy Highlights."""

import aiohttp
import asyncio
from datetime import datetime, timedelta
import logging

from .const import API_URL

_LOGGER = logging.getLogger(__name__)


class BirdfyHighlightsApiError(Exception):
    """Exception for API errors."""


class BirdfyHighlightsApi:
    """API client for Birdfy Highlights."""

    def __init__(self, uuid: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._uuid = uuid
        self._session = session

    async def async_get_highlights(
        self, start_time: int | None = None, end_time: int | None = None
    ) -> dict:
        """Fetch highlights data from the API."""
        params = {"uuid": self._uuid}

        if start_time is not None:
            params["startTime"] = str(start_time)
        if end_time is not None:
            params["endTime"] = str(end_time)

        try:
            async with self._session.get(
                API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if data.get("message"):
                    raise BirdfyHighlightsApiError(data["message"])

                return data

        except aiohttp.ClientError as err:
            raise BirdfyHighlightsApiError(f"Error communicating with API: {err}")
        except asyncio.TimeoutError:
            raise BirdfyHighlightsApiError("Timeout communicating with API")

    async def async_get_today(self) -> dict:
        """Fetch today's highlights."""
        now = datetime.now()
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1) - timedelta(milliseconds=1)

        start_time = int(start.timestamp() * 1000)
        end_time = int(end.timestamp() * 1000)

        return await self.async_get_highlights(start_time, end_time)

    async def async_validate_uuid(self) -> bool:
        """Validate that the UUID is valid by making a test request."""
        try:
            data = await self.async_get_highlights()
            # If we get data back (even empty), the UUID is valid
            return "birdList" in data or "dataList" in data or data.get("dateRange")
        except BirdfyHighlightsApiError:
            return False
