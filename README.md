# Birdfy Highlights for Home Assistant

A Home Assistant integration that exposes bird species data from your Birdfy feeder camera.

## Features

- **Bird Species Count**: Number of unique species observed today
- **Last Bird Species**: Most recently detected bird species
- **New Species Today**: Count of first-time visitors
- **Bird Species List**: Complete list of all species with thumbnails and video links

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "Birdfy Highlights" and install it
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/birdfy_highlights` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Birdfy Highlights"
4. Enter your Highlight UUID

### Finding Your UUID

Your UUID can be found from the Birdfy mobile app's share feature. Look for a link like:

```
https://highlight.birdfy.com/?uuid=YOUR_UUID_HERE
```

The UUID is the value after `uuid=`.

## Sensors

This integration creates the following sensors:

| Sensor | Description | Attributes |
|--------|-------------|------------|
| `sensor.birdfy_highlights_bird_species_count` | Number of species today | `species_list`, `thumbnails` |
| `sensor.birdfy_highlights_last_bird_species` | Last detected species | `title`, `category`, `video_url`, `detection_time` |
| `sensor.birdfy_highlights_new_species_today` | Count of new species | `new_species` |
| `sensor.birdfy_highlights_bird_species_today` | Comma-separated species list | All data including highlights |

## Example Automations

### Notify on New Bird Species

```yaml
automation:
  - alias: "New Bird Species Alert"
    trigger:
      - platform: state
        entity_id: sensor.birdfy_highlights_new_species_today
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          title: "New Bird Visitor!"
          message: "A new species was spotted: {{ state_attr('sensor.birdfy_highlights_last_bird_species', 'title') }}"
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
            {{ states('sensor.birdfy_highlights_bird_species_count') }} species visited today:
            {{ states('sensor.birdfy_highlights_bird_species_today') }}
```

## Data Update

The integration polls the Birdfy API every 15 minutes by default.

## Support

For issues and feature requests, please open an issue on GitHub.

## License

MIT License
