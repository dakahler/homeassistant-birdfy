# Birdfy for Home Assistant

A Home Assistant integration that exposes bird species data from your Birdfy feeder camera.

## Features

- **Bird Species Count**: Number of unique species observed today
- **Last Bird Species**: Most recently detected bird species
- **New Species Today**: Count of first-time visitors
- **Bird Species List**: Complete list of all species with thumbnails and video links
- **Full Moments Feed** (via optional Birdfy Account Login):
  - **Bundled Lovelace Card (`custom:birdfy-moments-card`)**: Auto-registered camera hero card with a pop-out modal dialog, species filter pills, scrollable Moments timeline, and inline MP4 video playback
  - **Moments Count**: Total motion/moment events recorded
  - **Moment Bird Visits**: Total bird visits with per-species visit counts
  - **Moments Species Count**: Unique species detected in Moments
  - **Last Moment**: Most recent moment's species/label, signed MP4 video URL, snapshot URL, and AI labels
  - **Moments Feed**: Full chronological list of recent moments and species counts
  - **Last Moment Image**: High-resolution snapshot entity of the latest moment
  - **Home Assistant Event (`birdfy_new_moment`)**: Fired automatically when a new moment is detected

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "Birdfy" and install it
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/birdfy` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Birdfy"
4. Enter your Highlight UUID (and/or your Birdfy Email & Password for the Moments feed)

### Finding Your UUID

Your UUID can be found from the Birdfy mobile app's share feature. Look for a link like:

```
https://highlight.birdfy.com/?uuid=YOUR_UUID_HERE
https://recap.birdfy.com/?uuid=YOUR_UUID_HERE
```

The UUID is the value after `uuid=`.

## Sensors

This integration creates the following sensors:

| Sensor | Description | Attributes |
|--------|-------------|------------|
| `sensor.birdfy_bird_species_count` | Number of species today | `species_list`, `thumbnails` |
| `sensor.birdfy_last_bird_species` | Last detected species | `title`, `category`, `video_url`, `detection_time` |
| `sensor.birdfy_new_species_today` | Count of new species | `new_species` |
| `sensor.birdfy_bird_species_today` | Comma-separated species list | All data including highlights |

### Moments Entities (Per Feeder Device)

When configured with your Birdfy account credentials, the integration also creates per-device Moments entities:

| Entity | Description | Attributes |
|--------|-------------|------------|
| `sensor.birdfy_moments_<device>_moments_count` | Total moments recorded | `date_range`, `start_time`, `end_time` |
| `sensor.birdfy_moments_<device>_moment_bird_visits` | Total bird visits | `species_counts`, `animal_visits`, `collected_count` |
| `sensor.birdfy_moments_<device>_moments_species_count` | Unique species in Moments | `species_list`, `species_counts` |
| `sensor.birdfy_moments_<device>_last_moment` | Latest moment species/label | `alarm_id`, `ai_labels`, `video_url`, `image_url`, `detection_time` |
| `sensor.birdfy_moments_<device>_moments_feed` | Comma-separated species list | Full `moments` list, `species_counts`, `total_moments`, `bird_visits` |
| `image.birdfy_moments_<device>_last_moment` | Snapshot of the latest moment | `alarm_id`, `species`, `ai_labels`, `image_url`, `video_url`, `detection_time` |

## Bundled Lovelace Card (`custom:birdfy-moments-card`)

The integration bundles and automatically registers the **Birdfy Moments Card** (`custom:birdfy-moments-card`)—no separate HACS frontend plugin or manual resource configuration is required.

1. Open your dashboard, click **Edit Dashboard > Add Card**, and select **Birdfy Moments Card** from the card picker (it automatically detects your feeder's Moments entities).
2. Or configure it in YAML:

```yaml
type: custom:birdfy-moments-card
title: Birdfy Moments
feed_entity: sensor.birdfy_moments_feeder_moments_feed
image_entity: image.birdfy_moments_feeder_last_moment
```

Clicking the camera snapshot opens a pop-out modal with species filter pills, a chronological Moments list, and an inline MP4 video player.

## Example Automations

### Notify on New Bird Species

```yaml
automation:
  - alias: "New Bird Species Alert"
    trigger:
      - platform: state
        entity_id: sensor.birdfy_new_species_today
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          title: "New Bird Visitor!"
          message: "A new species was spotted: {{ state_attr('sensor.birdfy_last_bird_species', 'title') }}"
```

### Daily Bird Summary

```yaml
automation:
  - alias: "Daily Bird Summary"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Today's Bird Report"
          message: >
            {{ states('sensor.birdfy_bird_species_count') }} species visited today:
            {{ states('sensor.birdfy_bird_species_today') }}
```

### Notify on Every New Moment (with Snapshot)

```yaml
automation:
  - alias: "Birdfy New Moment Alert"
    trigger:
      - platform: event
        event_type: birdfy_new_moment
    action:
      - service: notify.mobile_app
        data:
          title: "Birdfy: {{ trigger.event.data.species }}"
          message: "Spotted at {{ trigger.event.data.device_name }}!"
          data:
            image: "{{ trigger.event.data.image_url }}"
            url: "{{ trigger.event.data.video_url }}"
```

## Data Update

The integration polls the Birdfy API every 15 minutes by default (and polls the Moments feed every 5 minutes).

## Support

For issues and feature requests, please open an issue on GitHub.

## License

MIT License
