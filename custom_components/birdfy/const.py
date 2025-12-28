"""Constants for the Birdfy integration."""

DOMAIN = "birdfy"

CONF_UUID = "uuid"
CONF_DATE_RANGE = "date_range"
CONF_SUBENTRY_NAME = "name"

# Subentry types
SUBENTRY_TYPE_DATE_RANGE = "date_range"

API_URL = "https://api2.nvts.co/moments/h5CuratedData"

# Update interval in minutes
DEFAULT_SCAN_INTERVAL = 15

# Date range options
DATE_RANGE_TODAY = "today"
DATE_RANGE_YESTERDAY = "yesterday"
DATE_RANGE_LAST_7_DAYS = "last_7_days"
DATE_RANGE_LAST_14_DAYS = "last_14_days"
DATE_RANGE_LAST_30_DAYS = "last_30_days"
DATE_RANGE_THIS_WEEK = "this_week"
DATE_RANGE_THIS_MONTH = "this_month"
DATE_RANGE_ALL_TIME = "all_time"

DEFAULT_DATE_RANGE = DATE_RANGE_TODAY

DATE_RANGE_OPTIONS = [
    DATE_RANGE_TODAY,
    DATE_RANGE_YESTERDAY,
    DATE_RANGE_LAST_7_DAYS,
    DATE_RANGE_LAST_14_DAYS,
    DATE_RANGE_LAST_30_DAYS,
    DATE_RANGE_THIS_WEEK,
    DATE_RANGE_THIS_MONTH,
    DATE_RANGE_ALL_TIME,
]

# Attributes
ATTR_SPECIES_COUNT = "species_count"
ATTR_SPECIES_LIST = "species_list"
ATTR_HIGHLIGHTS = "highlights"
ATTR_NEW_SPECIES = "new_species"
ATTR_LAST_DETECTION = "last_detection"
ATTR_THUMBNAILS = "thumbnails"
ATTR_DATE_RANGE = "date_range"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
