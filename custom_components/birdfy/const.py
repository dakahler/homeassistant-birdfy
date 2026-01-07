"""Constants for the Birdfy integration."""

DOMAIN = "birdfy"

CONF_UUID = "uuid"
CONF_RECAP_UUID = "recap_uuid"
CONF_DATE_RANGE = "date_range"
CONF_SUBENTRY_NAME = "name"

# Subentry types
SUBENTRY_TYPE_DATE_RANGE = "date_range"

API_URL = "https://api2.nvts.co/moments/h5CuratedData"
RECAP_API_URL = "https://api2.nvts.co/moments/community/recapData"

# Update interval in minutes
DEFAULT_SCAN_INTERVAL = 15
RECAP_SCAN_INTERVAL = 60  # Recap data changes less frequently

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

# Attributes - Highlights
ATTR_SPECIES_COUNT = "species_count"
ATTR_SPECIES_LIST = "species_list"
ATTR_HIGHLIGHTS = "highlights"
ATTR_NEW_SPECIES = "new_species"
ATTR_LAST_DETECTION = "last_detection"
ATTR_THUMBNAILS = "thumbnails"
ATTR_DATE_RANGE = "date_range"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"

# Attributes - Recap
ATTR_RECAP_DATE = "statistics_date"
ATTR_RECAP_DURATION = "duration"
ATTR_RECAP_EVENT_COUNT = "event_count"
ATTR_RECAP_BIRD_SPECIES_COUNT = "bird_species_count"
ATTR_RECAP_BIRD_VISITS = "bird_visits"
ATTR_RECAP_SPECIES_SURPASSES = "species_surpasses_percent"
ATTR_RECAP_VISITS_SURPASSES = "visits_surpasses_percent"
ATTR_RECAP_TOP_BIRD = "top_bird"
ATTR_RECAP_UNCOMMON_BIRD = "uncommon_bird"
ATTR_RECAP_UNCOMMON_SURPASSES = "uncommon_surpasses_percent"
ATTR_RECAP_HUMMINGBIRD_SPECIES = "hummingbird_species_count"
ATTR_RECAP_HUMMINGBIRD_VISITS = "hummingbird_visits"
ATTR_RECAP_VIDEO_HIGHLIGHTS = "video_highlights"
ATTR_RECAP_VIDEO_TOP_BIRD = "video_top_bird"
ATTR_RECAP_VIDEO_UNCOMMON = "video_uncommon"
ATTR_RECAP_VIDEO_BUSIEST = "video_busiest"
ATTR_RECAP_VIDEO_HUMMINGBIRD = "video_hummingbird"
