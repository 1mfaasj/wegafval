"""Config flow voor Wegafval RWM kalender."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.storage import Store

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
    STORAGE_VERSION,
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


def _adres_schema(invoer: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_POSTCODE, default=invoer.get(CONF_POSTCODE, "")): str,
            vol.Required(
                CONF_HUISNUMMER, default=invoer.get(CONF_HUISNUMMER, vol.UNDEFINED)
            ): cv.positive_int,
            vol.Optional(CONF_TOEVOEGING, default=invoer.get(CONF_TOEVOEGING) or ""): str,
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

    def _reconfigure_entry(self) -> ConfigEntry | None:
        if self.source != SOURCE_RECONFIGURE:
            return None
        return self.hass.config_entries.async_get_entry(self.context["entry_id"])

    # ------------------------------------------------------------------
    # Adres zoeken (nieuw of wijzigen)
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._adres_stap("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._reconfigure_entry()
        huidig = dict(entry.data) if entry else {}
        return await self._adres_stap("reconfigure", user_input, huidig)

    async def _adres_stap(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        standaard: dict[str, Any],
    ) -> ConfigFlowResult:
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
                        try:
                            return await self._adres_gekozen(adressen[0])
                        except RWMError:
                            errors["base"] = "cannot_connect"
                    else:
                        self._kandidaten = adressen
                        return await self.async_step_select_address()

        return self.async_show_form(
            step_id=step_id,
            data_schema=_adres_schema(user_input or standaard),
            errors=errors,
        )

    async def async_step_select_address(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            adres = next(a for a in self._kandidaten if str(a["bagid"]) == user_input[CONF_BAGID])
            try:
                return await self._adres_gekozen(adres)
            except RWMError:
                errors["base"] = "cannot_connect"

        opties = [
            SelectOptionDict(value=str(a["bagid"]), label=a.get("description") or str(a["bagid"]))
            for a in self._kandidaten
        ]
        return self.async_show_form(
            step_id="select_address",
            data_schema=vol.Schema(
                {vol.Required(CONF_BAGID): SelectSelector(SelectSelectorConfig(options=opties))}
            ),
            errors=errors,
        )

    async def _adres_gekozen(self, adres: dict[str, Any]) -> ConfigFlowResult:
        """Verwerk het gekozen adres; geeft RWMError door bij netwerkproblemen."""
        bagid = str(adres["bagid"])
        entry = self._reconfigure_entry()

        if entry is None or entry.unique_id != bagid:
            await self.async_set_unique_id(bagid)
            self._abort_if_unique_id_configured()

        # Zonder afvalstromen kunnen we niet bepalen of de papierstap nodig is;
        # de fout gaat daarom naar het formulier in plaats van stil verder te gaan.
        stromen = parse_stromen(await self._client().afvalstromen(bagid))
        self._adres = adres
        self._kernen = kernen_uit_stromen(stromen)
        if self._kernen:
            return await self.async_step_papier()
        return await self._afronden(GEEN_PAPIER)

    async def async_step_papier(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self._afronden(user_input[CONF_PAPIER_KERN])

        standaard = GEEN_PAPIER
        if entry := self._reconfigure_entry():
            huidig = entry.options.get(CONF_PAPIER_KERN, GEEN_PAPIER)
            if huidig in self._kernen:
                standaard = huidig

        return self.async_show_form(
            step_id="papier", data_schema=_papier_schema(self._kernen, standaard)
        )

    # ------------------------------------------------------------------
    # Afronden
    # ------------------------------------------------------------------

    def _entry_data(self) -> tuple[str, dict[str, Any]]:
        a = self._adres
        omschrijving = a.get("description") or f"{a.get('postcode')} {a.get('huisnummer')}"
        return omschrijving, {
            CONF_BAGID: str(a["bagid"]),
            CONF_POSTCODE: a.get("postcode"),
            CONF_HUISNUMMER: a.get("huisnummer"),
            CONF_ADRES: omschrijving,
        }

    async def _afronden(self, kern: str) -> ConfigFlowResult:
        titel, data = self._entry_data()

        entry = self._reconfigure_entry()
        if entry is None:
            return self.async_create_entry(
                title=titel,
                data=data,
                options={CONF_PAPIER_KERN: kern},
            )

        await self._wijzig_adres(entry, titel, data, kern)
        return self.async_abort(reason="reconfigure_successful")

    async def _wijzig_adres(
        self,
        entry: ConfigEntry,
        titel: str,
        data: dict[str, Any],
        kern: str,
    ) -> None:
        """Zet een bestaande entry over naar een nieuw adres."""
        hass = self.hass
        oud_bagid = str(entry.data[CONF_BAGID])
        nieuw_bagid = data[CONF_BAGID]

        # Eerst uitladen, zodat de coordinator geen oude gegevens meer opslaat
        await hass.config_entries.async_unload(entry.entry_id)

        if oud_bagid != nieuw_bagid:
            # Entiteiten en apparaat behouden (entity-ID's, namen, automations)
            ent_reg = er.async_get(hass)
            for entiteit in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
                if entiteit.unique_id.startswith(f"{oud_bagid}_"):
                    ent_reg.async_update_entity(
                        entiteit.entity_id,
                        new_unique_id=nieuw_bagid + entiteit.unique_id[len(oud_bagid) :],
                    )

            dev_reg = dr.async_get(hass)
            for apparaat in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
                if (DOMAIN, oud_bagid) in apparaat.identifiers:
                    dev_reg.async_update_device(
                        apparaat.id,
                        new_identifiers=(apparaat.identifiers - {(DOMAIN, oud_bagid)})
                        | {(DOMAIN, nieuw_bagid)},
                    )

        # De cache hoort bij het oude adres
        await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()

        hass.config_entries.async_update_entry(
            entry,
            unique_id=nieuw_bagid,
            title=titel,
            data=data,
            options={**entry.options, CONF_PAPIER_KERN: kern},
        )

        await hass.config_entries.async_setup(entry.entry_id)

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
            stromen = parse_stromen(await client.afvalstromen(self.config_entry.data[CONF_BAGID]))
        except RWMError:
            return self.async_abort(reason="cannot_connect")

        kernen = kernen_uit_stromen(stromen)
        huidig = self.config_entry.options.get(CONF_PAPIER_KERN, GEEN_PAPIER)
        if huidig not in kernen:
            huidig = GEEN_PAPIER
        return self.async_show_form(step_id="init", data_schema=_papier_schema(kernen, huidig))
