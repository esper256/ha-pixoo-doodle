# Device evidence

## Pixoo 16, hardware 201

On November 25, 2026, Divoom’s same-LAN discovery returned hardware 201 for the owner's Wi-Fi Pixoo 16. The LAN API accepted JSON POSTs at port 80 on `/post`. Port 9000 refused connections. Initial discovery and configuration polling returned no firmware version. The diagnostic firmware sensor consequently reports unknown.

| Operation | Observed result |
| --- | --- |
| Channel/GetAllConf | Brightness, clock ID, rotation, mirror and time-format fields. No screen power field. |
| Channel/GetIndex | Current channel in SelectIndex. |
| Channel/GetClockInfo | Current clock ID and brightness. |
| Draw/GetHttpGifId | PicId was 1 before drawing and after one reset and single-frame upload. |
| Channel/SetBrightness | Setting the current level was acknowledged and read back at 20%. |
| Draw/ResetHttpGifId, Draw/SendHttpGif | An RGB frame of exactly 768 bytes before base64 encoding, with PicID 1 and no PicWidth, displayed correctly. The owner visually confirmed a green check mark during a 20-second test. |
| Channel/SetClockSelectId, Channel/SetIndex | The original face and channel were restored and verified by polling. |
| Device/GetHardwareVersion, Sys/GetUtcTime, Tools/GetTimerStatus on port 80 | String-valued error_code indicating the request was rejected. |

A separate temporary installation of Core 2026.11.3 completed the manual-IP config flow against the real panel, loaded its entities, read brightness and channel through the registered get_config action, produced redacted diagnostics, and unloaded the entry. The test made no changes to the owner’s Home Assistant installation.

The single-frame test exercised the client's normal upload path. Animated GIFs, scroll timing, buzzer, timers and changes to system settings have automated or protocol coverage only. The scrubbed response fixture is in [tests/fixtures/pixoo16.json](../tests/fixtures/pixoo16.json).

Targeted unicast SSDP and mDNS queries elicited no reply. Reverse DNS supplied no model-specific hostname. A DHCP lease hostname in UniFi has not been established. The integration matches DHCP updates for already registered MACs only. A shared ESP chipset prefix is insufficient evidence for new-device discovery.

## Other hardware

| Hardware | Endpoint and identification | Implemented scope |
| --- | --- | --- |
| 90, 92 | Pixoo 64, POST port 80, DeviceToken | Square RGB frames, native text, channel and clock controls, tools |
| 96 | Pixoo 64, POST port 9000 | Same drawing and controls, no token |
| 400 | Times Gate, POST port 80, LocalToken | Whole-device power, brightness, mirror, 24-hour mode, whole clock and tools |
| 402 | Times Gate, POST port 9000 | Same controls. Reads brightness and power separately because GetAllConf can return an empty success acknowledgement. |
| 510, 511, 512 | Times Frame, GET with a JSON body, port 9000 | Whole-device controls, clock selection and tools |
| 530 | AstroToo, POST port 9000 | Power, brightness, 24-hour mode and tools |

Port 9000 uses `/divoom_api`. The vendor's LAN checks report Times Frame firmware 510175/511175 and AstroToo 530062. These models have synthetic transport tests here. Gate, Frame and AstroToo have different media formats from the square RGB displays. Their v0.1 entities and actions cover whole-device control. The Gate's resolution sensor refers to one of its five LCDs.

There is third-party software with a 32-pixel canvas. A Wi-Fi Pixoo 32 hardware ID, wire payload and sample have yet to be established. Bluetooth Pixoo Max and Pixoo devices require a separate transport.

[Official Pixoo 16 API](https://doc.divoom-gz.com/web/#/12/489) · [Vendor protocol notes](https://github.com/DivoomDevelop/divoom-wifi-python/blob/main/docs/PROTOCOL.md) · [Vendor LAN verification](https://github.com/DivoomDevelop/divoom-wifi-python/blob/main/docs/LAN_CHECKS.md) · [Third-party Pixoo toolkit](https://github.com/cyanheads/pixoo-toolkit)


## v0.2 validation

Cloud feed selection uses the Pixoo 16 and 64 documented indices 0 (recommended), 1 (favorites), and 2 (subscribed artists). The Pixoo 16 page also labels index 3 Album while giving a range of 0–2. That index is omitted pending confirmation. The selector and media playback were tested on simulated displays. Catalog discovery and decoding of a native 16×16 animation were checked against the public website independently of any device. [Pixoo 16 cloud-channel documentation](https://doc.divoom-gz.com/web/#/12/484)
