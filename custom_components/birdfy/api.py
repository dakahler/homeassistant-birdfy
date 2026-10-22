"""API client for Birdfy."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any
import uuid as uuid_lib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from .const import (
    API_URL,
    AUTH_BASE_URL,
    CENTRAL_API_BASE_URL,
    DATE_RANGE_ALL_TIME,
    DATE_RANGE_LAST_7_DAYS,
    DATE_RANGE_LAST_14_DAYS,
    DATE_RANGE_LAST_30_DAYS,
    DATE_RANGE_THIS_MONTH,
    DATE_RANGE_THIS_WEEK,
    DATE_RANGE_TODAY,
    DATE_RANGE_YESTERDAY,
    DEFAULT_UCID,
    MOMENTS_BASE_URL_TEMPLATE,
    MOMENTS_DEFAULT_BASE_URL,
    RECAP_API_URL,
)

_LOGGER = logging.getLogger(__name__)

# Netvue API return codes
RET_OK = 0
RET_USER_SIGNATURE_INVALID = 73
RET_TIME_INVALID = 84
RET_TOKEN_EXPIRED = 113
RET_REFRESH_TOKEN_NOT_MATCH = 117
RET_REFRESH_TOKEN_EXPIRED = 118
RET_USER_HAS_NEVER_LOGIN = 128

IGNORED_AI_LABELS = {"no bird", "no_bird", "nobird", "not a bird"}
GENERIC_AI_LABELS = {
    "person",
    "human",
    "pet",
    "vehicle",
    "package",
    "animal",
    "bird",
    "squirrel",
}
LABEL_MASK_NAMES = ["person", "pet", "vehicle", "package", "animal", "bird", "bird"]
AI_LABEL_DICT_KEYS = {"commonname", "desc", "label", "name", "species", "tag"}
BIRDFY_PRODUCT_CODE_RE = re.compile(r"^[PQ][A-Z0-9]{2}$")
TAG_PREFIX_RE = re.compile(r"^\d+_")


def get_timezone(tz_name: str | None) -> ZoneInfo | None:
    """Resolve an IANA timezone name safely."""
    if not tz_name:
        return None
    try:
        return ZoneInfo(str(tz_name))
    except (ZoneInfoNotFoundError, ValueError):
        return None


def get_date_range_timestamps(
    date_range: str, tz_name: str | None = None
) -> tuple[int | None, int | None]:
    """Calculate start and end timestamps for a given date range option.

    Returns timestamps in milliseconds, or (None, None) for all_time.
    """
    tz = get_timezone(tz_name)
    now = datetime.now(tz) if tz else datetime.now()
    today_start = datetime(now.year, now.month, now.day, tzinfo=tz)

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
        start = datetime(now.year, now.month, 1, tzinfo=tz)
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


def _md5_hex(value: str) -> str:
    """Return MD5 hex digest of a string (used by Netvue login v2)."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _compute_nvs_signature(
    token: str, ucid: str, udid: str, user_id: str | int, timestamp_ms: str | int
) -> str:
    """Compute Netvue v2 chained HMAC-SHA256 request signature."""

    def _hmac(key: str, msg: str) -> str:
        return hmac.new(
            key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    k1 = _hmac(f"nvs1{token}", str(ucid))
    k2 = _hmac(k1, str(udid))
    k3 = _hmac(k2, str(user_id))
    k4 = _hmac(k3, str(timestamp_ms))
    return _hmac(k4, "nvs1_request")


def normalize_species_label(
    raw_label: str, tag_map: dict[str, str] | None = None
) -> str:
    """Convert raw Netvue tag/species keys into human-readable display names."""
    cleaned = str(raw_label or "").strip()
    if not cleaned:
        return ""

    # Check if there is a parenthetical attribute like "Northern Cardinal (male)"
    attr = None
    match = re.match(r"^(.+?)\s*\(\s*([^()]+?)\s*\)\s*$", cleaned)
    if match:
        base_name = match.group(1).strip()
        attr = match.group(2).strip()
    else:
        base_name = cleaned

    lower = base_name.lower()
    if tag_map and lower in tag_map:
        resolved = tag_map[lower]
    elif TAG_PREFIX_RE.match(base_name):
        # e.g. "3_northern_cardinal" -> "Northern Cardinal"
        stripped = TAG_PREFIX_RE.sub("", base_name).replace("_", " ").strip()
        resolved = tag_map.get(stripped.lower(), stripped.title()) if tag_map else stripped.title()
    else:
        resolved = base_name

    if attr:
        return f"{resolved} ({attr})"
    return resolved


def extract_event_labels(
    event: dict[str, Any], tag_map: dict[str, str] | None = None
) -> list[str]:
    """Extract and normalize AI recognition species/labels from a Moment event."""
    description_obj: dict[str, Any] = {}
    raw_desc = event.get("description")
    if isinstance(raw_desc, str) and raw_desc.strip():
        try:
            parsed = json.loads(raw_desc)
            if isinstance(parsed, dict):
                description_obj = parsed
        except ValueError:
            pass
    elif isinstance(raw_desc, dict):
        description_obj = raw_desc

    sources = [
        event.get("aiLabels"),
        (event.get("extra") or {}).get("motion", {}).get("aiLabels")
        if isinstance(event.get("extra"), dict)
        else None,
        description_obj.get("aiLabels"),
    ]

    found: dict[str, str] = {}

    def _walk(node: Any, collect_strings: bool = True) -> None:
        if isinstance(node, str):
            if collect_strings:
                for part in node.split(","):
                    item = part.strip()
                    if not item:
                        continue
                    norm_Check = re.sub(r"[\s_-]+", " ", item.lower())
                    if norm_Check in IGNORED_AI_LABELS:
                        continue
                    display = normalize_species_label(item, tag_map)
                    if display and display.lower() not in found:
                        found[display.lower()] = display
        elif isinstance(node, list):
            for elem in node:
                _walk(elem, collect_strings)
        elif isinstance(node, dict):
            for k, v in node.items():
                key_matches = str(k).lower() in AI_LABEL_DICT_KEYS
                if key_matches or isinstance(v, (dict, list)):
                    _walk(v, key_matches)

    for src in sources:
        if src is not None:
            _walk(src, True)

    labels = list(found.values())

    # Prefer specific species names over generic labels ("bird", "animal", etc.) when present
    specific = [lbl for lbl in labels if lbl.lower() not in GENERIC_AI_LABELS]
    if specific:
        return specific
    if labels:
        return labels

    # Fallback to bitmask labelMask if present
    label_mask = event.get("labelMask")
    if isinstance(label_mask, int) and label_mask > 0:
        mask_labels: list[str] = []
        for idx, name in enumerate(LABEL_MASK_NAMES):
            if label_mask & (1 << idx):
                title = name.title()
                if title not in mask_labels:
                    mask_labels.append(title)
        return mask_labels

    return []


class BirdfyHighlightsApiError(Exception):
    """Exception for API errors."""


class BirdfyRecapApiError(Exception):
    """Exception for Recap API errors."""


class BirdfyMomentsApiError(Exception):
    """Exception for Moments/Account API errors."""


class BirdfyAuthError(BirdfyMomentsApiError):
    """Exception for authentication errors."""


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


class BirdfyRecapApi:
    """API client for Birdfy Monthly Recap."""

    def __init__(self, uuid: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._uuid = uuid
        self._session = session

    async def async_get_recap(self, need_history: bool = True) -> dict:
        """Fetch recap data from the API."""
        params = {"uuid": self._uuid}
        if need_history:
            params["needHistory"] = "1"

        _LOGGER.debug("Fetching recap with params: %s", params)

        try:
            async with self._session.get(
                RECAP_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                # Handle 204 No Content
                if response.status == 204:
                    raise BirdfyRecapApiError("No recap data available (may have expired)")

                response.raise_for_status()

                # Check for empty response
                content_length = response.headers.get("content-length")
                if content_length == "0":
                    raise BirdfyRecapApiError("No recap data available (empty response)")

                data = await response.json()

                if data.get("message"):
                    raise BirdfyRecapApiError(data["message"])

                return data

        except aiohttp.ClientError as err:
            raise BirdfyRecapApiError(f"Error communicating with Recap API: {err}")
        except asyncio.TimeoutError:
            raise BirdfyRecapApiError("Timeout communicating with Recap API")

    async def async_validate_uuid(self) -> bool:
        """Validate that the recap UUID is valid by making a test request."""
        try:
            data = await self.async_get_recap()
            # If we get data with statistics fields, the UUID is valid
            return (
                "statisticsDate" in data
                or "birdSpeciesCount" in data
                or "eventCount" in data
            )
        except BirdfyRecapApiError:
            return False


class BirdfyAccountApi:
    """Authenticated API client for Birdfy Account and Moments feed."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        refresh_token: str | None = None,
        user_id: int | str | None = None,
        region: str | None = None,
        udid: str | None = None,
    ) -> None:
        """Initialize the authenticated Birdfy API client."""
        self._session = session
        self._username = username
        self._password = password
        self._token = token or ""
        self._refresh_token = refresh_token or ""
        self._user_id = int(user_id) if user_id is not None and str(user_id).isdigit() else (user_id or 0)
        self._region = region or ""
        self._ucid = DEFAULT_UCID
        self._udid = udid or f"web-{uuid_lib.uuid4().hex}"
        self._clock_skew_ms = 0
        self._auth_lock = asyncio.Lock()
        self._tag_cache: dict[str, dict[str, str]] = {}

    @property
    def token(self) -> str:
        """Return current access token."""
        return self._token

    @property
    def refresh_token(self) -> str:
        """Return current refresh token."""
        return self._refresh_token

    @property
    def user_id(self) -> int | str:
        """Return current user ID."""
        return self._user_id

    @property
    def region(self) -> str:
        """Return user region."""
        return self._region

    @property
    def udid(self) -> str:
        """Return client UDID."""
        return self._udid

    def _moments_base_url(self, region: str | None = None) -> str:
        """Build regional Moments API base URL."""
        reg = (region or self._region or "").strip()
        if reg:
            return MOMENTS_BASE_URL_TEMPLATE.format(region=reg)
        return MOMENTS_DEFAULT_BASE_URL

    def _build_headers(self, signed: bool = True) -> dict[str, str]:
        """Build Netvue headers, optionally including v2 HMAC signature."""
        headers = {
            "x-nvs-ucid": self._ucid,
            "x-nvs-udid": self._udid,
            "accept-language": "en",
        }
        if signed:
            headers["x-nvs-version"] = '{"signature":2}'
            if self._token and self._user_id:
                now_ms = int(time.time() * 1000) - self._clock_skew_ms
                ts_str = str(now_ms)
                uid_str = str(self._user_id)
                sig = _compute_nvs_signature(
                    self._token, self._ucid, self._udid, uid_str, ts_str
                )
                headers["x-nvs-userid"] = uid_str
                headers["x-nvs-time"] = ts_str
                headers["x-nvs-signature"] = sig
        return headers

    async def async_login(
        self, username: str | None = None, password: str | None = None
    ) -> dict[str, Any]:
        """Authenticate with email/username and password."""
        user = (username or self._username or "").strip()
        pwd = password if password is not None else (self._password or "")
        if not user or not pwd:
            raise BirdfyAuthError("Username and password are required")

        # Hash password with MD5 if not already a 32-char hex digest
        pwd_hash = (
            pwd.lower()
            if re.fullmatch(r"[0-9a-fA-F]{32}", pwd)
            else _md5_hex(pwd)
        )

        payload = {
            "username": user,
            "password": pwd_hash,
            "locale": "en",
            "platform": 0,
        }

        url = f"{AUTH_BASE_URL}users/login/v2"
        try:
            async with self._session.post(
                url,
                json=payload,
                headers=self._build_headers(signed=False),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400 or (
                    isinstance(data, dict) and data.get("ret", 0) not in (0, None)
                ):
                    msg = (
                        data.get("msg")
                        if isinstance(data, dict)
                        else f"HTTP {response.status}"
                    )
                    raise BirdfyAuthError(f"Login failed: {msg}")

                if not isinstance(data, dict) or not data.get("token"):
                    raise BirdfyAuthError("Login response missing token")

                self._username = user
                self._password = pwd
                self._token = data["token"]
                self._refresh_token = data.get("refreshToken", "")
                self._user_id = data.get("userID", 0)
                self._region = data.get("region", "")
                return data

        except aiohttp.ClientError as err:
            raise BirdfyMomentsApiError(f"Error communicating with Auth API: {err}")
        except asyncio.TimeoutError:
            raise BirdfyMomentsApiError("Timeout communicating with Auth API")

    async def async_refresh_token(self) -> bool:
        """Refresh the access token using the refresh token or re-login."""
        async with self._auth_lock:
            if self._token and self._refresh_token:
                url = f"{AUTH_BASE_URL}auth/refreshtoken"
                payload = {
                    "token": self._token,
                    "refreshToken": self._refresh_token,
                }
                try:
                    async with self._session.post(
                        url,
                        json=payload,
                        headers=self._build_headers(signed=True),
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        data = await response.json(content_type=None)
                        if (
                            response.status == 200
                            and isinstance(data, dict)
                            and data.get("token")
                        ):
                            self._token = data["token"]
                            self._refresh_token = data.get(
                                "refreshToken", self._refresh_token
                            )
                            return True
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    _LOGGER.debug("Token refresh failed, falling back to login")

            if self._username and self._password:
                await self.async_login(self._username, self._password)
                return True

            return False

    async def _async_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        signed: bool = True,
        retry: bool = True,
    ) -> Any:
        """Make an authenticated request with automatic clock-skew & token retry."""
        if signed and not self._token:
            await self.async_login()

        clean_params = (
            {str(k): str(v) for k, v in params.items() if v is not None}
            if params
            else None
        )

        try:
            async with self._session.request(
                method,
                url,
                params=clean_params,
                json=json_data,
                headers=self._build_headers(signed=signed),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 204:
                    return {}

                data = await response.json(content_type=None)

                # Check for Netvue error envelope
                ret = data.get("ret") if isinstance(data, dict) else None
                if response.status >= 400 or (ret is not None and ret != RET_OK):
                    if retry and ret == RET_TIME_INVALID and isinstance(data, dict):
                        try:
                            msg_obj = json.loads(data.get("msg", "{}"))
                            server_time = int(msg_obj.get("time", 0))
                            if server_time > 0:
                                self._clock_skew_ms = (
                                    int(time.time() * 1000) - server_time
                                )
                                return await self._async_request(
                                    method,
                                    url,
                                    params=params,
                                    json_data=json_data,
                                    signed=signed,
                                    retry=False,
                                )
                        except (ValueError, TypeError):
                            pass

                    if retry and (
                        ret
                        in (
                            RET_USER_SIGNATURE_INVALID,
                            RET_TOKEN_EXPIRED,
                            RET_REFRESH_TOKEN_NOT_MATCH,
                            RET_REFRESH_TOKEN_EXPIRED,
                            RET_USER_HAS_NEVER_LOGIN,
                        )
                        or response.status in (401, 403)
                    ):
                        if await self.async_refresh_token():
                            return await self._async_request(
                                method,
                                url,
                                params=params,
                                json_data=json_data,
                                signed=signed,
                                retry=False,
                            )

                    msg = (
                        data.get("msg") or data.get("message")
                        if isinstance(data, dict)
                        else f"HTTP {response.status}"
                    )
                    raise BirdfyMomentsApiError(
                        f"API error ({url}): {msg} (ret={ret}, status={response.status})"
                    )

                return data

        except aiohttp.ClientError as err:
            raise BirdfyMomentsApiError(f"Error communicating with API ({url}): {err}")
        except asyncio.TimeoutError:
            raise BirdfyMomentsApiError(f"Timeout communicating with API ({url})")

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Fetch user devices from /devices/v3 and return Birdfy cameras."""
        url = f"{AUTH_BASE_URL}devices/v3"
        data = await self._async_request("GET", url, signed=True)
        raw_devices = data.get("devices", []) if isinstance(data, dict) else []

        birdfy_devices: list[dict[str, Any]] = []
        all_devices: list[dict[str, Any]] = []

        for dev in raw_devices:
            if not isinstance(dev, dict) or not dev.get("serialNumber"):
                continue
            ability_raw = dev.get("ability")
            if isinstance(ability_raw, str):
                try:
                    dev["ability"] = json.loads(ability_raw)
                except ValueError:
                    pass

            all_devices.append(dev)
            sn = str(dev.get("serialNumber", ""))
            product_code = str(dev.get("productCode", ""))
            if (
                BIRDFY_PRODUCT_CODE_RE.match(product_code)
                or (len(sn) >= 4 and sn[2] == "7")
                or "bird" in str(dev.get("deviceName", "")).lower()
            ):
                birdfy_devices.append(dev)

        return birdfy_devices if birdfy_devices else all_devices

    async def async_get_tag_list(self, region: str | None = None) -> dict[str, str]:
        """Fetch localized species tag names from /moments/tagList."""
        reg_key = (region or self._region or "default").lower()
        if reg_key in self._tag_cache:
            return self._tag_cache[reg_key]

        base = self._moments_base_url(region)
        url = f"{base}moments/tagList"
        tag_map: dict[str, str] = {}
        try:
            data = await self._async_request(
                "GET", url, params={"parentId": 0}, signed=True
            )
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    key = str(item.get("key") or "").strip()
                    loc_key = str(item.get("localizedKey") or "").strip()
                    if name:
                        for alias in (key, name, loc_key):
                            if alias:
                                tag_map[alias.lower()] = name
                        if key and TAG_PREFIX_RE.match(key):
                            stripped = TAG_PREFIX_RE.sub("", key).replace("_", " ").strip()
                            if stripped:
                                tag_map[stripped.lower()] = name
            self._tag_cache[reg_key] = tag_map
        except BirdfyMomentsApiError as err:
            _LOGGER.debug("Could not load tagList (non-fatal): %s", err)

        return tag_map

    async def async_get_moment_counts(
        self,
        serial_number: str,
        start_time: int | None,
        end_time: int | None,
        region: str | None = None,
    ) -> tuple[int | None, list[dict[str, Any]]]:
        """Fetch total moment count and per-species event counts for a time window."""
        if start_time is None or end_time is None:
            return None, []

        base = self._moments_base_url(region)
        count_url = f"{base}devices/events/countByTime"
        bird_count_url = f"{base}birdData/eventCount"

        async def _get_total() -> int | None:
            try:
                res = await self._async_request(
                    "GET",
                    count_url,
                    params={
                        "serialNumber": serial_number,
                        "queryStartTime": start_time,
                        "queryEndTime": end_time,
                    },
                )
                if isinstance(res, dict) and res.get("total") is not None:
                    return int(res["total"])
            except (BirdfyMomentsApiError, ValueError, TypeError) as err:
                _LOGGER.debug("countByTime failed: %s", err)
            return None

        async def _get_bird_counts() -> list[dict[str, Any]]:
            try:
                res = await self._async_request(
                    "GET",
                    bird_count_url,
                    params={
                        "serialnumber": serial_number,
                        "startTime": start_time,
                        "endTime": end_time,
                    },
                )
                if isinstance(res, dict):
                    return (
                        res.get("tagCountList")
                        or res.get("counts")
                        or res.get("birdCountList")
                        or []
                    )
            except BirdfyMomentsApiError as err:
                _LOGGER.debug("birdData/eventCount failed: %s", err)
            return []

        return await asyncio.gather(_get_total(), _get_bird_counts())

    async def async_get_moments_events(
        self,
        serial_number: str,
        date_range: str,
        tz_name: str | None = None,
        region: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch Moment events for a device and date range."""
        base = self._moments_base_url(region)
        start_time, end_time = get_date_range_timestamps(date_range, tz_name)

        # For single-day queries (today / yesterday), try /events/bydate/{YYYYMMDD} first
        if date_range in (DATE_RANGE_TODAY, DATE_RANGE_YESTERDAY) and start_time:
            tz = get_timezone(tz_name)
            dt = (
                datetime.fromtimestamp(start_time / 1000, tz=tz)
                if tz
                else datetime.fromtimestamp(start_time / 1000)
            )
            date_compact = dt.strftime("%Y%m%d")
            bydate_url = f"{base}devices/{serial_number}/events/bydate/{date_compact}"
            params: dict[str, Any] = {
                "limit": limit,
                "ignoreAiLabels": "false",
            }
            if tz_name:
                params["tz"] = tz_name
            if end_time:
                params["endTime"] = end_time

            try:
                data = await self._async_request("GET", bydate_url, params=params)
                if isinstance(data, dict) and isinstance(data.get("events"), list):
                    return data["events"]
            except BirdfyMomentsApiError as err:
                _LOGGER.debug(
                    "events/bydate failed, falling back to /events: %s", err
                )

        # Multi-day or fallback: use /devices/{sn}/events
        events_url = f"{base}devices/{serial_number}/events"
        params = {
            "limit": limit,
            "ignoreAiLabels": "false",
            "reverse": 1,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        data = await self._async_request("GET", events_url, params=params)
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return data["events"]
        return []

    async def async_resolve_media(
        self,
        serial_number: str,
        events: list[dict[str, Any]],
    ) -> dict[Any, dict[str, list[str]]]:
        """Resolve signed video and snapshot URLs via centralapi.nvts.co/event/downloadLink."""
        if not events:
            return {}

        event_list_payload = []
        for ev in events:
            alarm_id = ev.get("alarmId")
            if alarm_id is None:
                continue

            desc_obj: dict[str, Any] = {}
            raw_desc = ev.get("description")
            if isinstance(raw_desc, str) and raw_desc.strip():
                try:
                    parsed = json.loads(raw_desc)
                    if isinstance(parsed, dict):
                        desc_obj = parsed
                except ValueError:
                    pass

            pic_list_raw = ev.get("pictureList")
            pic_list: list[str] = []
            if isinstance(pic_list_raw, list):
                pic_list = [str(x) for x in pic_list_raw if x]
            elif isinstance(pic_list_raw, str) and pic_list_raw.strip():
                try:
                    parsed_pics = json.loads(pic_list_raw)
                    if isinstance(parsed_pics, list):
                        pic_list = [str(x) for x in parsed_pics if x]
                    else:
                        pic_list = [pic_list_raw.strip()]
                except ValueError:
                    pic_list = [
                        p.strip() for p in pic_list_raw.split(",") if p.strip()
                    ]

            event_list_payload.append(
                {
                    "serialnumber": serial_number,
                    "alarmId": alarm_id,
                    "dataGroup": ["video", "pic"],
                    "recordDir": desc_obj.get("recordDir"),
                    "recordUrl": desc_obj.get("recordUrl"),
                    "pic": ev.get("pic"),
                    "pictureList": pic_list,
                    "labelMask": ev.get("labelMask"),
                    "type": ev.get("type"),
                }
            )

        if not event_list_payload:
            return {}

        url = f"{CENTRAL_API_BASE_URL}event/downloadLink"
        resolved: dict[Any, dict[str, list[str]]] = {}
        try:
            data = await self._async_request(
                "POST",
                url,
                json_data={"eventList": event_list_payload},
                signed=True,
            )
            if isinstance(data, dict) and isinstance(data.get("eventList"), list):
                for item in data["eventList"]:
                    if not isinstance(item, dict):
                        continue
                    aid = item.get("alarmId")
                    videos = [
                        str(v).strip()
                        for v in (item.get("videoFileList") or [])
                        if isinstance(v, str) and v.strip().startswith("http")
                    ]
                    pics = [
                        str(p).strip()
                        for p in (item.get("picList") or [])
                        if isinstance(p, str) and p.strip().startswith("http")
                    ]
                    if aid is not None:
                        resolved[aid] = {"videos": videos, "images": pics}
        except BirdfyMomentsApiError as err:
            _LOGGER.debug("event/downloadLink failed (non-fatal): %s", err)

        return resolved
