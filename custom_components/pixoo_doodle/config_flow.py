"""Identification, LAN connection testing and entry options."""

from ipaddress import IPv4Address

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .coordinator import DOMAIN
from .divoom_client import Client, DeviceError, InvalidToken, Json, request
from .divoom_client.cloud import discover
from .divoom_client.models import MODELS

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def identity(row: Json) -> str:
    if mac := row.get("DeviceMac"):
        return str(mac).replace(":", "").replace("-", "").lower()
    return str(row["DeviceId"])


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.rows: dict[str, Json] = {}
        self.pending: Json = {}
        self.target: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["manual", "cloud"])

    async def async_step_cloud(self, user_input=None):
        if user_input is not None:
            return await self._identify(self.rows[user_input["device"]])
        try:
            rows = await discover(async_get_clientsession(self.hass))
        except DeviceError:
            return self.async_abort(reason="cloud_unreachable")
        self.rows = {
            identity(r): r
            for r in rows
            if str(r.get("Hardware")).isdigit() and int(r["Hardware"]) in MODELS
        }
        if not self.rows:
            return self.async_abort(reason="no_devices")
        options = {
            k: f"{v.get('DeviceName', 'Divoom')} ({v['DevicePrivateIP']})"
            for k, v in self.rows.items()
        }
        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
        )

    async def async_step_manual(self, user_input=None):
        return await self._host_form("manual", user_input)

    async def async_step_reconfigure(self, user_input=None):
        self.target = self._get_reconfigure_entry()
        return await self._host_form("reconfigure", user_input)

    async def _host_form(self, step, user_input):
        error = None
        if user_input is not None:
            try:
                host = str(IPv4Address(user_input["host"]))
                session = async_get_clientsession(self.hass)
                try:
                    row = await request(
                        session,
                        "POST",
                        f"http://{host}:9000/divoom_api",
                        {"Command": "Device/GetHardwareVersion"},
                    )
                except DeviceError:
                    row = {}
                if not (
                    row.get("Hardware")
                    and (row.get("DeviceMac") or row.get("DeviceId"))
                ):
                    row = next(
                        (
                            r
                            for r in await discover(session)
                            if r["DevicePrivateIP"] == host
                        ),
                        {},
                    )
                if row:
                    return await self._identify({**row, "DevicePrivateIP": host})
                error = "identity_missing"
            except ValueError:
                error = "invalid_host"
            except DeviceError:
                error = "cloud_unreachable"
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "host", default=self.target.data["host"] if self.target else ""
                    ): str
                }
            ),
            errors={"base": error} if error else {},
        )

    async def _identify(self, row):
        try:
            hw = int(row["Hardware"])
        except TypeError, ValueError, KeyError:
            return self.async_abort(reason="unknown_hardware")
        if hw not in MODELS:
            return self.async_abort(reason="unknown_hardware")
        uid = identity(row)
        await self.async_set_unique_id(uid)
        if self.target:
            self._abort_if_unique_id_mismatch()
        else:
            self._abort_if_unique_id_configured()
        self.pending = {"host": row["DevicePrivateIP"], "hardware": hw}
        if row.get("DeviceMac"):
            self.pending["mac"] = uid
        if row.get("DeviceId"):
            self.pending["device_id"] = str(row["DeviceId"])
        if self.target and self.target.data.get("token"):
            self.pending["token"] = self.target.data["token"]
        if MODELS[hw].token_field and not self.pending.get("token"):
            return await self.async_step_token()
        return await self._finish()

    async def _finish(self):
        client = Client(
            async_get_clientsession(self.hass),
            self.pending["host"],
            self.pending["hardware"],
            self.pending.get("token"),
        )
        try:
            await client.probe()
        except InvalidToken:
            return self._token_form("invalid_auth")
        except DeviceError:
            return self.async_abort(reason="cannot_connect")
        if self.target:
            return self.async_update_reload_and_abort(self.target, data=self.pending)
        return self.async_create_entry(title=client.model.name, data=self.pending)

    def _token_form(self, error=None):
        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema({vol.Required("token"): PASSWORD}),
            errors={"base": error} if error else {},
        )

    async def async_step_token(self, user_input=None):
        if user_input is None:
            return self._token_form()
        self.pending["token"] = user_input["token"]
        return await self._finish()

    async def async_step_reauth(self, entry_data):
        self.target = self._get_reauth_entry()
        self.pending = dict(self.target.data)
        return await self.async_step_token()

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        await self.async_set_unique_id(discovery_info.macaddress)
        self._abort_if_unique_id_configured(updates={"host": discovery_info.ip})
        return self.async_abort(reason="unknown_hardware")


class OptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "poll_interval", default=opts.get("poll_interval", 30)
                    ): vol.All(int, vol.Range(min=5, max=3600)),
                    vol.Required(
                        "push_throttle", default=opts.get("push_throttle", 1)
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=60)),
                    vol.Required(
                        "default_font", default=opts.get("default_font", "small")
                    ): vol.In(["small", "large"]),
                }
            ),
        )
