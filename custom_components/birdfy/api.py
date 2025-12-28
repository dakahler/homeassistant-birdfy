"""API client for Birdfy."""

import aiohttp
import asyncio
from datetime import datetime, timedelta
import logging

from .const import (
    API_URL,
    DATE_RANGE_TODAY,
    DATE_RANGE_YESTERDAY,
    DATE_RANGE_LAST_7_DAYS,
    DATE_RANGE_LAST_14_DAYS,
    DATE_RANGE_LAST_30_DAYS,
    DATE_RANGE_THIS_WEEK,
    DATE_RANGE_THIS_MONTH,
    DATE_RANGE_ALL_TIME,
)

_LOGGER = logging.getLogger(__name__)


def get_date_range_timestamps(date_range: str) -> tuple[int | None, int | None]:
    """Calculate start and end timestamps for a given date range option.

    Returns timestamps in milliseconds, or (None, None) for all_time.
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)

    if date_range == DATE_RANGE_TODAY:
        start = today_start
        end = start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_YESTERDAY:
        start = today_start - timedelta(days=1)
        end = today_start - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_LAST_7_DAYS:
        start = today_start - timedelta(days=6)
        end = today_start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_LAST_14_DAYS:
        start = today_start - timedelta(days=13)
        end = today_start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_LAST_30_DAYS:
        start = today_start - timedelta(days=29)
        end = today_start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_THIS_WEEK:
        # Start from Monday of current week
        days_since_monday = now.weekday()
        start = today_start - timedelta(days=days_since_monday)
        end = today_start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_THIS_MONTH:
        start = datetime(now.year, now.month, 1)
        end = today_start + timedelta(days=1) - timedelta(milliseconds=1)

    elif date_range == DATE_RANGE_ALL_TIME:
        return None, None

    else:
        # Default to today
        start = today_start
        end = start + timedelta(days=1) - timedelta(milliseconds=1)

    start_time = int(start.timestamp() * 1000)
    end_time = int(end.timestamp() * 1000)

    return start_time, end_time


class BirdfyHighlightsApiError(Exception):
    """Exception for API errors."""


class BirdfyHighlightsApi:
    """API client for Birdfy."""

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

        _LOGGER.debug("Fetching highlights with params: %s", params)

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

    async def async_get_for_date_range(self, date_range: str) -> dict:
        """Fetch highlights for a specific date range option."""
        start_time, end_time = get_date_range_timestamps(date_range)
        return await self.async_get_highlights(start_time, end_time)

    async def async_get_today(self) -> dict:
        """Fetch today's highlights."""
        return await self.async_get_for_date_range(DATE_RANGE_TODAY)

    async def async_validate_uuid(self) -> bool:
        """Validate that the UUID is valid by making a test request."""
        try:
            data = await self.async_get_highlights()
            # If we get data back (even empty), the UUID is valid
            return "birdList" in data or "dataList" in data or data.get("dateRange")
        except BirdfyHighlightsApiError:
            return False
