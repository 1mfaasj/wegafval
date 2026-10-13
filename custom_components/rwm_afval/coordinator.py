"""Data-coordinator: haalt RWM-data op en bewaart een lokale cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RWMClient, RWMConnectionError, RWMError
from .const import (
    CONF_BAGID,
    CONF_PAPIER_KERN,
    DOMAIN,
    GEEN_PAPIER,
    PAPIER_STREAM_ID,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .parsing import kernen_uit_stromen, parse_kalender, parse_stromen

_LOGGER = logging.getLogger(__name__)


@dataclass
class RWMData:
    """Ophaaldata per afvalstroom."""

    streams: dict[str, dict[str, Any]]  # id -> {"title", "icon"}
    pickups: dict[str, list[date]]  # id -> gesorteerde datums
    bijgewerkt: datetime

    def volgende(self, sid: str, vanaf: date) -> date | None:
        return next((d for d in self.pickups.get(sid, []) if d >= vanaf), None)

    def op_datum(self, datum: date) -> list[str]:
        return [sid for sid, datums in self.pickups.items() if datum in datums]

    def titel(self, sid: str) -> str:
        return self.streams.get(sid, {}).get("title", sid)

    def als_dict(self) -> dict[str, Any]:
        return {
            "streams": self.streams,
            "pickups": {k: [d.isoformat() for d in v] for k, v in self.pickups.items()},
            "bijgewerkt": self.bijgewerkt.isoformat(),
        }

    @classmethod
    def uit_dict(cls, ruw: dict[str, Any]) -> RWMData:
        return cls(
            streams={
                k: {"title": v["title"], "icon": v.get("icon")} for k, v in ruw["streams"].items()
            },
            pickups={k: [date.fromisoformat(d) for d in v] for k, v in ruw["pickups"].items()},
            bijgewerkt=datetime.fromisoformat(ruw["bijgewerkt"]),
        )


class RWMCoordinator(DataUpdateCoordinator[RWMData]):
    """Haalt de afvalkalender op; valt bij storing terug op de laatste data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = RWMClient(async_create_clientsession(hass))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    async def _haal_op(self) -> RWMData:
        bagid = self.config_entry.data[CONF_BAGID]
        vandaag = dt_util.now().date()

        stromen = parse_stromen(await self.client.afvalstromen(bagid))
        pickups: dict[str, set[date]] = {}

        for jaar in (vandaag.year, vandaag.year + 1):
            try:
                kal = await self.client.kalender(bagid, jaar)
            except RWMConnectionError:
                if jaar == vandaag.year:
                    raise
                kal = None  # volgend jaar is vaak nog niet gepubliceerd
            for sid, datums in parse_kalender(kal).items():
                pickups.setdefault(sid, set()).update(datums)

        # De afvalstromen-lijst bevat ook de eerstvolgende datum per stroom
        for sid, stroom in stromen.items():
            if stroom["next"]:
                pickups.setdefault(sid, set()).add(stroom["next"])

        if not pickups:
            raise RWMError("RWM gaf geen ophaaldata terug")

        streams = {
            sid: {
                "title": stromen.get(sid, {}).get("title", f"Afvalstroom {sid}"),
                "icon": stromen.get(sid, {}).get("icon"),
            }
            for sid in pickups
        }

        kern = self.config_entry.options.get(CONF_PAPIER_KERN, GEEN_PAPIER)
        if kern and kern != GEEN_PAPIER:
            schema = kernen_uit_stromen(stromen).get(kern)
            if schema is None:
                _LOGGER.warning(
                    "Oud-papierschema voor '%s' niet meer gevonden bij RWM; "
                    "kies de kern opnieuw via Configureren",
                    kern,
                )
            else:
                pickups[PAPIER_STREAM_ID] = set(
                    schema.datums(vandaag.year, vandaag.year)
                    + schema.datums(vandaag.year + 1, vandaag.year)
                )
                streams[PAPIER_STREAM_ID] = {"title": "Oud papier", "icon": "papieren-doos"}

        return RWMData(
            streams=streams,
            pickups={sid: sorted(d) for sid, d in pickups.items()},
            bijgewerkt=dt_util.utcnow(),
        )

    async def _async_update_data(self) -> RWMData:
        try:
            data = await self._haal_op()
        except RWMError as err:
            if self.data is not None:
                _LOGGER.warning("RWM niet bereikbaar (%s); laatst bekende data blijft actief", err)
                return self.data
            if (cache := await self._store.async_load()) is not None:
                try:
                    data = RWMData.uit_dict(cache)
                except (KeyError, TypeError, ValueError):
                    raise UpdateFailed(f"RWM niet bereikbaar: {err}") from err
                _LOGGER.warning("RWM niet bereikbaar (%s); opgeslagen data wordt gebruikt", err)
                return data
            raise UpdateFailed(f"RWM niet bereikbaar: {err}") from err

        await self._store.async_save(data.als_dict())
        return data
