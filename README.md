# Pixoo Doodle

Control a Divoom Wi-Fi display from Home Assistant. Draw on a Pixoo 16 or 64, show an image, scroll a message, or use a display as a light and clock in an automation. Normal polling and drawing use the local network.

| Display | Support in v0.1 |
| --- | --- |
| Wi-Fi Pixoo 16 (201) | Verified on hardware. The owner visually confirmed a 16×16 drawing. Brightness and clock restoration passed readback. |
| Pixoo 64 (90/92/96) | Protocol-based support for both endpoint generations. Tested with simulated replies. |
| Times Gate (400/402), Times Frame (510/511/512), AstroToo (530) | Protocol-based whole-device controls and tools. Drawing is limited to Pixoo 16 and 64. |
| Pixoo 32 | Awaiting an identifiable Wi-Fi sample. Bluetooth-only models need another transport. |

[Device evidence and command coverage](docs/devices.md)

<!-- ha-marketplace:exclude-start -->
## Installation

In Home Assistant 2026.11 or newer, open **Settings → Marketplace → Add from link**, enter `https://github.com/esper256/ha-pixoo-doodle`, install **Pixoo Doodle** and restart Home Assistant. In HACS, use **Custom repositories**, choose the **Integration** category and download the integration.
<!-- ha-marketplace:exclude-end -->

## Connect a display

Open **Settings → Devices & services → Add integration → Pixoo Doodle**. Choose **Find displays with Divoom** or enter an IPv4 address. Leave the panel powered on and connected to Wi-Fi. Initial identification of older displays uses Divoom's discovery service. Home Assistant and the display must share a public IP for that lookup. Hardware 90, 92 and 400 prompt for a LAN token from the device settings.

**Configure** sets the poll interval (5–3600 seconds, default 30), minimum time between frame uploads (1–60 seconds, default 1) and local pixel font size. Use **Reconfigure** after an address change. Removing the integration entry removes the device from Home Assistant.

## Controls and actions

Open the device page for power, brightness and model-specific controls. Pixoo displays include channel, clock face, visualizer, custom page, rotation and a last-drawing image. The clock selector starts with the current face. Use `get_faces` with a dial category such as `Social` to populate more choices. Firmware, endpoint and hardware sensors help with troubleshooting. The buzzer test and supported restart buttons are disabled by default.

In **Developer tools → Actions**, select the device or pass its config entry ID as `config_entry_id`. Pixel coordinates start at the top left. Colors use `#RRGGBB`. These script steps target a display chosen in the action editor. Replace `YOUR_DEVICE_ID` with its Home Assistant device ID.

```yaml
sequence:
  - action: pixoo_doodle.fill
    target: {device_id: YOUR_DEVICE_ID}
    data: {color: "#001018", commit: false}
  - action: pixoo_doodle.draw_line
    target: {device_id: YOUR_DEVICE_ID}
    data: {points: [[1, 13], [14, 13]], color: "#42ff85"}
  - action: pixoo_doodle.draw_text
    target: {device_id: YOUR_DEVICE_ID}
    data: {text: "OK", font: small, align: center, color: "#ffffff"}
```

Use `draw_rect` (optional `filled`), `draw_pixels`, `fill` or `clear` with `commit: false` to stage changes. The next committed edit sends the whole canvas. Request response data from a drawing action or call `get_canvas` to receive the preview PNG as base64 keyed by entry ID.

```yaml
sequence:
  - action: pixoo_doodle.show_image
    target: {device_id: YOUR_DEVICE_ID}
    data: {source: "media-source://media_source/local/flower.png", fit: crop}
  - action: pixoo_doodle.play_gif
    target: {device_id: YOUR_DEVICE_ID}
    data: {source: "media-source://media_source/local/weather.gif", fit: fit, dither: true}
```

Images can also come from an HTTP(S) URL or an absolute path in Home Assistant's `allowlist_external_dirs`. Home Assistant fetches and resizes the file before it reaches the display. Inputs are limited to 8 MiB and four megapixels. The preview shows the first frame of the most recent successful drawing.

### Laundry notification

```yaml
alias: Laundry finished on Pixoo
triggers:
  - trigger: state
    entity_id: binary_sensor.washer_running
    from: "on"
    to: "off"
actions:
  - action: pixoo_doodle.scroll_text
    target: {device_id: YOUR_DEVICE_ID}
    data: {text: "Laundry ready", color: "#55ffaa", speed: 100}
```

Other actions include `set_timer` (minute, second, status), `stopwatch` (0 pause, 1 start, 2 reset), `scoreboard` (red and blue scores), `play_buzzer`, `select_clock_face` (clock_id) and `refresh`. Query actions return font metadata, pages of clock IDs or a shareable device configuration with `get_fonts`, `get_faces` and `get_config`.

## Troubleshooting

- **Discovery finds nothing.** Check the display is on Wi-Fi and review VPNs, multiple WANs and outbound HTTPS access. Unknown hardware IDs require a verified model profile.
- **Device unavailable.** Allow Home Assistant to reach the panel on TCP 80 or 9000 through the IoT VLAN. Some Pixoo 64 firmware contacts Divoom and an MQTT broker after a cold boot before opening its local API. Restore the required outbound connectivity and allow time for startup. HA retries locally.
- **Power or firmware is unknown.** The tested Pixoo 16 omits power and firmware in its settings reply. Power becomes available after a successful power command and remains an estimate on this firmware.
- **Animations take time.** Uploads are serialized and paced. A 40-frame animation takes at least 39 seconds to transfer. Some firmware shows a loading overlay. Use one drawing controller per display because other apps share its picture counter.
- **Image did not load.** Check the source, dimensions and Home Assistant access. HTTP redirects are declined. The panel receives resized RGB frames directly. Long URLs and incorrectly sized GIF files never reach its decoder.

Pixoo Doodle is independent of Divoom. Thanks to Divoom for its protocol documentation and to gickowtf and cyanheads for documenting behavior on real devices. [Official protocol](https://github.com/DivoomDevelop/divoom-wifi-python) · [gickowtf integration](https://github.com/gickowtf/pixoo-homeassistant) · [Credits and licenses](NOTICE)
