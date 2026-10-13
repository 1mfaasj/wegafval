"""Config flow voor RWM Afvalkalender."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import RWMClient, RWMError, normaliseer_postcode
from .const import (
    CONF_ADRES,
    CONF_BAGID,
    CONF_HUISNUMMER,
    CONF_PAPIER_KERN,
    CONF_POSTCODE,
    CONF_TOEVOEGING,
    DOMAIN,
    GEEN_PAPIER,
)
from .parsing import PapierSchema, kernen_uit_stromen, parse_stromen


def _toev(waarde: Any) -> str:
    return re.sub(r"[\s\-]", "", str(waarde or "")).lower()


def _papier_schema(kernen: dict[str, PapierSchema], standaard: str) -> vol.Schema:
    opties = [SelectOptionDict(value=GEEN_PAPIER, label="Geen / niet van toepassing")]
    opties += [
        SelectOptionDict(value=naam, label=f"{naam} — {schema.omschrijving}")
        for naam, schema in kernen.items()
    ]
    return vol.Schema(
        {
            vol.Required(CONF_PAPIER_KERN, default=standaard): SelectSelector(
                SelectSelectorConfig(options=opties, mode=SelectSelectorMode.DROPDOWN)
            )
        }
    )


class RWMConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adres opzoeken bij RWM en (optioneel) de oud-papierkern kiezen."""

    VERSION = 1

    def __init__(self) -> None:
        self._kandidaten: list[dict[str, Any]] = []
        self._adres: dict[str, Any] = {}
        self._kernen: dict[str, PapierSchema] = {}

    def _client(self) -> RWMClient:
        return RWMClient(async_get_clientsession(self.hass))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            postcode = normaliseer_postcode(user_input[CONF_POSTCODE])
            if not re.fullmatch(r"\d{4}[A-Z]{2}", postcode):
                errors[CONF_POSTCODE] = "invalid_postcode"
            else:
                try:
                    adressen = await self._client().zoek_adres(
                        postcode, user_input[CONF_HUISNUMMER]
                    )
                except RWMError:
                    errors["base"] = "cannot_connect"
                else:
                    if toev := _toev(user_input.get(CONF_TOEVOEGING)):
                        adressen = [
                            a
                            for a in adressen
                            if _toev(f"{a.get('huisletter') or ''}{a.get('toevoeging') or ''}")
                            == toev
                        ]
                    if not adressen:
                        errors["base"] = "address_not_found"
                    elif len(adressen) == 1:
                        return await self._adres_gekozen(adressen[0])
                    else:
                        self._kandidaten = adressen
                        return await self.async_step_select_address()

        invoer = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POSTCODE, default=invoer.get(CONF_POSTCODE, "")): str,
                    vol.Required(
                        CONF_HUISNUMMER, default=invoer.get(CONF_HUISNUMMER, vol.UNDEFINED)
                    ): cv.positive_int,
                    vol.Optional(CONF_TOEVOEGING, default=invoer.get(CONF_TOEVOEGING, "")): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_address(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            adres = next(
                a for a in self._kandidaten if str(a["bagid"]) == user_input[CONF_BAGID]
            )
            return await self._adres_gekozen(adres)

        opties = [
            SelectOptionDict(value=str(a["bagid"]), label=a.get("description") or str(a["bagid"]))
            for a in self._kandidaten
        ]
        return self.async_show_form(
            step_id="select_address",
            data_schema=vol.Schema(
                {vol.Required(CONF_BAGID): SelectSelector(SelectSelectorConfig(options=opties))}
            ),
        )

    async def _adres_gekozen(self, adres: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(str(adres["bagid"]))
        self._abort_if_unique_id_configured()
        self._adres = adres
        try:
            stromen = parse_stromen(await self._client().afvalstromen(str(adres["bagid"])))
        except RWMError:
            stromen = {}
        self._kernen = kernen_uit_stromen(stromen)
        if self._kernen:
            return await self.async_step_papier()
        return self._maak_entry(GEEN_PAPIER)

    async def async_step_papier(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._maak_entry(user_input[CONF_PAPIER_KERN])
        return self.async_show_form(
            step_id="papier", data_schema=_papier_schema(self._kernen, GEEN_PAPIER)
        )

    def _maak_entry(self, kern: str) -> ConfigFlowResult:
        a = self._adres
        omschrijving = a.get("description") or f"{a.get('postcode')} {a.get('huisnummer')}"
        return self.async_create_entry(
            title=omschrijving,
            data={
                CONF_BAGID: str(a["bagid"]),
                CONF_POSTCODE: a.get("postcode"),
                CONF_HUISNUMMER: a.get("huisnummer"),
                CONF_ADRES: omschrijving,
            },
            options={CONF_PAPIER_KERN: kern},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RWMOptionsFlow()


class RWMOptionsFlow(OptionsFlow):
    """Oud-papierkern achteraf wijzigen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_PAPIER_KERN: user_input[CONF_PAPIER_KERN]})

        client = RWMClient(async_get_clientsession(self.hass))
        try:
            stromen = parse_stromen(
                await client.afvalstromen(self.config_entry.data[CONF_BAGID])
            )
        except RWMError:
            return self.async_abort(reason="cannot_connect")

        kernen = kernen_uit_stromen(stromen)
        huidig = self.config_entry.options.get(CONF_PAPIER_KERN, GEEN_PAPIER)
        if huidig not in kernen:
            huidig = GEEN_PAPIER
        return self.async_show_form(step_id="init", data_schema=_papier_schema(kernen, huidig))
