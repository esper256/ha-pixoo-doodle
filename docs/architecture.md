# Architecture

The hardware number selects a model, resolution, token field and HTTP method. Setup probes the preferred endpoint using a read. Polling can recover by probing the alternate endpoint. Writes are sent once, since a timeout can occur after the display has accepted a command.

The `divoom_client` package accepts an existing aiohttp session. It validates both status fields when present, serializes animations, and checks the number and byte length of every frame before issuing a write. A new drawing session resets the picture counter. After an interrupted animation, the next send starts from a reset. Resetting between animations limits counter growth. The scheduler spaces individual frame requests at least one second apart.

Home Assistant stores one coordinator on each config entry. Entities share its snapshots. Where firmware omits fields, controls can remember the last acknowledged change during the session. Reconfiguring a host checks its identity against the existing entry. DHCP changes can update an already registered MAC. Cloud discovery requires a shared public IP only during onboarding of devices without a local identity response.

Each square display has an in-memory working canvas and a separate PNG preview. A per-entry lock serializes edits, decoding and uploads. A failed upload leaves the last successful preview available. Pillow runs image decoding and font rendering in an executor. A GIF is composited, scaled and capped at 40 frames before the upload starts. Scroll animation samples longer strings across the available frames. On native-text firmware the preview approximates the device font. Reloading the entry clears the working canvas and preview.

To add hardware, supply a scrubbed identity response, status response, verified resolution and transport. Check operation-specific payloads and gate controls on evidence. For example the Times Gate expects JPEG frames with an LCD selection array. The square-display RGB writer cannot be reused unchanged.
