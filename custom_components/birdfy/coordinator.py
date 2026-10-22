"""DataUpdateCoordinator for Birdfy."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GENERIC_AI_LABELS,
    BirdfyAccountApi,
    BirdfyHighlightsApi,
    BirdfyHighlightsApiError,
    BirdfyMomentsApiError,
    BirdfyRecapApi,
    BirdfyRecapApiError,
    extract_event_labels,
    get_date_range_timestamps,
    normalize_species_label,
)
from .const import (
    DEFAULT_DATE_RANGE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_MOMENT,
    MOMENTS_SCAN_INTERVAL,
    RECAP_SCAN_INTERVAL,
)

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


class BirdfyMomentsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Birdfy Moments feed data for a device."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: BirdfyAccountApi,
        entry: ConfigEntry,
        device: dict[str, Any],
        subentry_id: str | None = None,
        date_range: str = DEFAULT_DATE_RANGE,
    ) -> None:
        """Initialize the Moments coordinator."""
        self.serial_number = str(device.get("serialNumber", ""))
        self.device_name = str(device.get("deviceName") or self.serial_number)
        self.device_region = str(device.get("region") or api.region or "")
        self.device_timezone = (
            str(device["timezone"]) if device.get("timezone") else None
        )
        self.device_info_raw = device

        suffix = f"{self.serial_number}_{subentry_id}" if subentry_id else self.serial_number
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_moments_{suffix}",
            update_interval=timedelta(minutes=MOMENTS_SCAN_INTERVAL),
        )
        self.api = api
        self.entry = entry
        self.subentry_id = subentry_id
        self._date_range = date_range
        self._last_seen_alarm_id: Any = None
        self._initialized_alarm_tracking = False

    @property
    def date_range(self) -> str:
        """Get the configured date range."""
        return self._date_range

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch Moments data from Netvue/Birdfy APIs."""
        try:
            date_range = self.date_range
            start_time, end_time = get_date_range_timestamps(
                date_range, self.device_timezone
            )

            tag_map = await self.api.async_get_tag_list(self.device_region)
            (total_count, raw_tag_counts), raw_events = await asyncio.gather(
                self.api.async_get_moment_counts(
                    self.serial_number,
                    start_time,
                    end_time,
                    region=self.device_region,
                ),
                self.api.async_get_moments_events(
                    self.serial_number,
                    date_range,
                    tz_name=self.device_timezone,
                    region=self.device_region,
                    limit=20,
                ),
            )

            # Normalize event timestamps and sort newest first
            valid_events: list[dict[str, Any]] = []
            for ev in raw_events:
                if not isinstance(ev, dict):
                    continue
                if not ev.get("alertTime") and ev.get("alertTimeTs"):
                    ev["alertTime"] = ev["alertTimeTs"]
                valid_events.append(ev)

            valid_events.sort(
                key=lambda x: int(x.get("alertTime") or 0), reverse=True
            )

            # Resolve signed video and snapshot URLs for the top events
            media_by_alarm = await self.api.async_resolve_media(
                self.serial_number, valid_events[:20]
            )

            # Parse species/category counts from /birdData/eventCount
            bird_visits: int | None = None
            animal_visits = 0
            collected_count = 0
            species_counts: dict[str, int] = {}

            for item in raw_tag_counts:
                if not isinstance(item, dict):
                    continue
                raw_tag = str(item.get("commonName") or item.get("tag") or "").strip()
                if not raw_tag:
                    continue
                try:
                    cnt = int(item.get("count", 0))
                except (ValueError, TypeError):
                    continue
                if cnt <= 0:
                    continue

                lower_tag = raw_tag.lower()
                if lower_tag == "all":
                    if total_count is None:
                        total_count = cnt
                elif lower_tag == "allbird":
                    bird_visits = cnt
                elif lower_tag == "allanimal":
                    animal_visits = cnt
                elif lower_tag == "collected":
                    collected_count = cnt
                else:
                    label = normalize_species_label(raw_tag, tag_map)
                    if label and label.lower() not in GENERIC_AI_LABELS:
                        species_counts[label] = species_counts.get(label, 0) + cnt

            # Build normalized moments list
            moments: list[dict[str, Any]] = []
            for ev in valid_events:
                alarm_id = ev.get("alarmId")
                alert_time = ev.get("alertTime")
                labels = extract_event_labels(ev, tag_map)
                primary_species = labels[0] if labels else "Motion"

                media = media_by_alarm.get(alarm_id, {})
                videos = media.get("videos", [])
                images = media.get("images", [])

                video_url = videos[0] if videos else None
                image_url = images[0] if images else None
                if not image_url:
                    raw_pic = str(ev.get("pic") or "").strip()
                    if raw_pic.startswith("http"):
                        image_url = raw_pic

                moments.append(
                    {
                        "alarm_id": alarm_id,
                        "time": alert_time,
                        "species": primary_species,
                        "ai_labels": labels,
                        "video_url": video_url,
                        "image_url": image_url,
                        "type": ev.get("type"),
                    }
                )

                # If eventCount didn't include a species found in recent events, include it
                for lbl in labels:
                    if (
                        lbl.lower() not in GENERIC_AI_LABELS
                        and lbl not in species_counts
                    ):
                        species_counts[lbl] = 1

            # Sort species_counts descending by visit count
            sorted_species_counts = dict(
                sorted(
                    species_counts.items(),
                    key=lambda kv: (-kv[1], kv[0]),
                )
            )
            species_list = list(sorted_species_counts.keys())

            if total_count is None:
                total_count = len(moments)

            if bird_visits is None:
                if sorted_species_counts:
                    bird_visits = sum(sorted_species_counts.values())
                else:
                    bird_visits = sum(
                        1
                        for m in moments
                        if m["ai_labels"]
                        and any(
                            l.lower() == "bird" or l.lower() not in GENERIC_AI_LABELS
                            for l in m["ai_labels"]
                        )
                    )

            last_moment = moments[0] if moments else None
            last_detection = last_moment.get("time") if last_moment else None

            # Fire Home Assistant event when a new moment is detected on the default coordinator
            if self.subentry_id is None and last_moment:
                latest_alarm_id = last_moment.get("alarm_id")
                if not self._initialized_alarm_tracking:
                    self._last_seen_alarm_id = latest_alarm_id
                    self._initialized_alarm_tracking = True
                elif (
                    latest_alarm_id is not None
                    and latest_alarm_id != self._last_seen_alarm_id
                ):
                    self._last_seen_alarm_id = latest_alarm_id
                    det_iso = (
                        datetime.fromtimestamp(last_detection / 1000).isoformat()
                        if last_detection
                        else None
                    )
                    self.hass.bus.async_fire(
                        EVENT_NEW_MOMENT,
                        {
                            "serial_number": self.serial_number,
                            "device_name": self.device_name,
                            "alarm_id": latest_alarm_id,
                            "species": last_moment.get("species"),
                            "ai_labels": last_moment.get("ai_labels", []),
                            "detection_time": det_iso,
                            "video_url": last_moment.get("video_url"),
                            "image_url": last_moment.get("image_url"),
                        },
                    )

            return {
                "total_moments": total_count,
                "bird_visits": bird_visits,
                "animal_visits": animal_visits,
                "collected_count": collected_count,
                "species_count": len(species_list),
                "species_list": species_list,
                "species_counts": sorted_species_counts,
                "moments": moments,
                "last_moment": last_moment,
                "last_detection": last_detection,
                "date_range": date_range,
                "start_time": start_time,
                "end_time": end_time,
            }

        except BirdfyMomentsApiError as err:
            raise UpdateFailed(f"Error fetching Moments data: {err}")
