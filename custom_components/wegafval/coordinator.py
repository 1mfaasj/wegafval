"""Data-coordinator voor Wegafval RWM kalender."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import RWMClient, RWMError
from .const import (
    CACHE_MAXIMUM_AGE,
    CACHE_WARNING_AGE,
    CONF_BAGID,
    CONF_PAPIER_KERN,
    DOMAIN,
    GEEN_PAPIER,
    PAPIER_STREAM_ID,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .parsing import (
    kernen_uit_stromen,
    parse_kalender,
    parse_stromen,
)

_LOGGER = logging.getLogger(__name__)

STATUS_ACTUEEL = "actueel"
STATUS_CACHE = "cache"
STATUS_VEROUDERD = "verouderd"

MAX_FUTURE_DAYS = 550


@dataclass
class RWMData:
    """Ophaaldata en bronstatus."""

    streams: dict[str, dict[str, Any]]
    pickups: dict[str, list[date]]
    bijgewerkt: datetime
    laatste_poging: datetime
    bron_status: str = STATUS_ACTUEEL
    laatste_fout: str | None = None

    def volgende(
        self,
        sid: str,
        vanaf: date,
    ) -> date | None:
        """Geef de eerstvolgende datum vanaf een bepaalde dag."""

        return next(
            (
                pickup_date
                for pickup_date in self.pickups.get(sid, [])
                if pickup_date >= vanaf
            ),
            None,
        )

    def op_datum(
        self,
        pickup_date: date,
    ) -> list[str]:
        """Geef alle afvalstromen die op een datum worden opgehaald."""

        return [
            sid
            for sid, pickup_dates in self.pickups.items()
            if pickup_date in pickup_dates
        ]

    def titel(
        self,
        sid: str,
    ) -> str:
        """Geef de zichtbare titel van een afvalstroom."""

        return self.streams.get(
            sid,
            {},
        ).get(
            "title",
            sid,
        )

    @property
    def cache_leeftijd(self) -> timedelta:
        """Geef de leeftijd van de laatst succesvolle gegevens."""

        now = dt_util.utcnow()

        try:
            age = now - self.bijgewerkt
        except TypeError:
            return timedelta(0)

        return max(
            age,
            timedelta(0),
        )

    @property
    def cache_leeftijd_uren(self) -> float:
        """Geef de cacheleeftijd in uren."""

        return round(
            self.cache_leeftijd.total_seconds() / 3600,
            1,
        )

    @property
    def is_verouderd(self) -> bool:
        """Geef aan of de cache ouder is dan 72 uur."""

        return self.cache_leeftijd > CACHE_WARNING_AGE

    @property
    def is_onbruikbaar_verouderd(self) -> bool:
        """Geef aan of de cache ouder is dan veertien dagen."""

        return self.cache_leeftijd > CACHE_MAXIMUM_AGE

    def met_fout(
        self,
        error: Exception,
        attempt_time: datetime,
    ) -> RWMData:
        """Maak een kopie met bijgewerkte foutstatus."""

        status = (
            STATUS_VEROUDERD
            if self.is_verouderd
            else STATUS_CACHE
        )

        return replace(
            self,
            laatste_poging=attempt_time,
            bron_status=status,
            laatste_fout=str(error),
        )

    def als_dict(self) -> dict[str, Any]:
        """Maak de gegevens geschikt voor lokale opslag."""

        return {
            "streams": self.streams,
            "pickups": {
                sid: [
                    pickup_date.isoformat()
                    for pickup_date in pickup_dates
                ]
                for sid, pickup_dates in self.pickups.items()
            },
            "bijgewerkt": self.bijgewerkt.isoformat(),
            "laatste_poging": self.laatste_poging.isoformat(),
            "bron_status": self.bron_status,
            "laatste_fout": self.laatste_fout,
        }

    @classmethod
    def uit_dict(
        cls,
        raw: dict[str, Any],
    ) -> RWMData:
        """Laad en valideer gegevens uit de lokale opslag."""

        if not isinstance(raw, dict):
            raise ValueError("Cache bevat geen object")

        raw_streams = raw.get("streams")
        raw_pickups = raw.get("pickups")
        raw_updated = raw.get("bijgewerkt")

        if not isinstance(raw_streams, dict):
            raise ValueError(
                "Cache bevat geen geldige afvalstromen"
            )

        if not isinstance(raw_pickups, dict):
            raise ValueError(
                "Cache bevat geen geldige ophaaldata"
            )

        if not isinstance(raw_updated, str):
            raise ValueError(
                "Cache bevat geen geldige updatedatum"
            )

        streams: dict[str, dict[str, Any]] = {}

        for sid, stream in raw_streams.items():
            if not isinstance(stream, dict):
                continue

            title = stream.get("title")

            if not isinstance(title, str):
                continue

            title = title.strip()

            if not title:
                continue

            streams[str(sid)] = {
                "title": title,
                "icon": stream.get("icon"),
            }

        pickups: dict[str, list[date]] = {}

        for sid, raw_dates in raw_pickups.items():
            if not isinstance(raw_dates, list):
                continue

            parsed_dates: set[date] = set()

            for raw_date in raw_dates:
                if not isinstance(raw_date, str):
                    continue

                try:
                    parsed_dates.add(
                        date.fromisoformat(raw_date)
                    )
                except ValueError:
                    continue

            if parsed_dates:
                pickups[str(sid)] = sorted(parsed_dates)

        if not streams:
            raise ValueError(
                "Cache bevat geen afvalstromen"
            )

        if not pickups:
            raise ValueError(
                "Cache bevat geen ophaaldata"
            )

        updated = datetime.fromisoformat(
            raw_updated
        )

        raw_attempt = raw.get("laatste_poging")

        if isinstance(raw_attempt, str):
            try:
                last_attempt = datetime.fromisoformat(
                    raw_attempt
                )
            except ValueError:
                last_attempt = updated
        else:
            last_attempt = updated

        last_error = raw.get("laatste_fout")

        return cls(
            streams=streams,
            pickups=pickups,
            bijgewerkt=updated,
            laatste_poging=last_attempt,
            bron_status=str(
                raw.get(
                    "bron_status",
                    STATUS_CACHE,
                )
            ),
            laatste_fout=(
                str(last_error)
                if last_error
                else None
            ),
        )


class RWMCoordinator(DataUpdateCoordinator[RWMData]):
    """Haal RWM-data op en gebruik geldige cache bij storingen."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )

        self.client = RWMClient(
            async_create_clientsession(hass)
        )

        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}",
        )

        self._update_lock = asyncio.Lock()
        self._was_unavailable = False
        self._reload_scheduled = False

    @property
    def paper_issue_id(self) -> str:
        """Geef het unieke ID van de papierkernmelding."""

        return (
            f"papierkern_verdwenen_"
            f"{self.config_entry.entry_id}"
        )

    @staticmethod
    def _validate_data(
        data: RWMData,
        today: date,
    ) -> None:
        """Controleer of nieuwe gegevens bruikbaar zijn."""

        if not data.streams:
            raise RWMError(
                "RWM gaf geen afvalstromen terug"
            )

        if not data.pickups:
            raise RWMError(
                "RWM gaf geen ophaaldata terug"
            )

        future_limit = today + timedelta(
            days=MAX_FUTURE_DAYS
        )

        future_count = 0

        for sid, pickup_dates in data.pickups.items():
            if sid not in data.streams:
                raise RWMError(
                    f"Afvalstroom {sid} heeft geen beschrijving"
                )

            if not pickup_dates:
                raise RWMError(
                    f"Afvalstroom {sid} heeft geen ophaaldatums"
                )

            if pickup_dates != sorted(set(pickup_dates)):
                raise RWMError(
                    f"Afvalstroom {sid} bevat dubbele "
                    "of ongesorteerde datums"
                )

            for pickup_date in pickup_dates:
                if pickup_date > future_limit:
                    raise RWMError(
                        "RWM gaf een onwaarschijnlijke datum terug: "
                        f"{pickup_date.isoformat()}"
                    )

                if pickup_date >= today:
                    future_count += 1

        if future_count == 0:
            raise RWMError(
                "RWM gaf geen toekomstige ophaaldata terug"
            )

    def _validate_against_previous(
        self,
        new_data: RWMData,
        today: date,
    ) -> None:
        """Detecteer extreme afwijkingen van eerdere gegevens."""

        if self.data is None:
            return

        old_future_dates = {
            pickup_date
            for pickup_dates in self.data.pickups.values()
            for pickup_date in pickup_dates
            if pickup_date >= today
        }

        new_future_dates = {
            pickup_date
            for pickup_dates in new_data.pickups.values()
            for pickup_date in pickup_dates
            if pickup_date >= today
        }

        if (
            len(old_future_dates) >= 6
            and not new_future_dates
        ):
            raise RWMError(
                "Nieuwe RWM-data bevat plotseling geen "
                "toekomstige ophaaldatums"
            )

    def _handle_paper_schema(
        self,
        selected_area: str,
        streams_from_api: dict[str, dict[str, Any]],
        pickups: dict[str, set[date]],
        streams: dict[str, dict[str, Any]],
        today: date,
    ) -> None:
        """Voeg het berekende papierschema toe."""

        if (
            not selected_area
            or selected_area == GEEN_PAPIER
        ):
            ir.async_delete_issue(
                self.hass,
                DOMAIN,
                self.paper_issue_id,
            )
            return

        paper_schema = kernen_uit_stromen(
            streams_from_api
        ).get(
            selected_area
        )

        if paper_schema is None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.paper_issue_id,
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="papierkern_verdwenen",
                translation_placeholders={
                    "kern": selected_area,
                },
            )

            _LOGGER.warning(
                "Oud-papierschema voor '%s' is niet meer "
                "gevonden bij RWM; kies de kern opnieuw via "
                "Configureren",
                selected_area,
            )
            return

        ir.async_delete_issue(
            self.hass,
            DOMAIN,
            self.paper_issue_id,
        )

        pickups[PAPIER_STREAM_ID] = set(
            paper_schema.datums(
                today.year,
                today.year,
            )
            + paper_schema.datums(
                today.year + 1,
                today.year,
            )
        )

        streams[PAPIER_STREAM_ID] = {
            "title": "Oud papier",
            "icon": "papieren-doos",
        }

    async def _haal_op(self) -> RWMData:
        """Haal en valideer actuele gegevens bij RWM."""

        bagid = self.config_entry.data[CONF_BAGID]
        now = dt_util.utcnow()
        today = dt_util.now().date()

        raw_streams = await self.client.afvalstromen(
            bagid
        )

        streams_from_api = parse_stromen(
            raw_streams
        )

        if not streams_from_api:
            raise RWMError(
                "RWM gaf geen geldige afvalstromen terug"
            )

        pickups: dict[str, set[date]] = {}
        calendar_items_found = 0

        for year in (
            today.year,
            today.year + 1,
        ):
            try:
                raw_calendar = await self.client.kalender(
                    bagid,
                    year,
                )
            except RWMError:
                if year == today.year:
                    raise

                raw_calendar = None

            parsed_calendar = parse_kalender(
                raw_calendar
            )

            for sid, pickup_dates in parsed_calendar.items():
                calendar_items_found += len(
                    pickup_dates
                )

                pickups.setdefault(
                    sid,
                    set(),
                ).update(
                    pickup_dates
                )

        for sid, stream in streams_from_api.items():
            next_pickup = stream.get("next")

            if next_pickup is not None:
                pickups.setdefault(
                    sid,
                    set(),
                ).add(
                    next_pickup
                )

        if not pickups:
            raise RWMError(
                "RWM gaf geen ophaaldata terug"
            )

        if calendar_items_found == 0:
            _LOGGER.warning(
                "RWM gaf geen kalenderregels terug; alleen "
                "eerstvolgende datums zijn beschikbaar"
            )

        streams = {
            sid: {
                "title": streams_from_api.get(
                    sid,
                    {},
                ).get(
                    "title",
                    f"Afvalstroom {sid}",
                ),
                "icon": streams_from_api.get(
                    sid,
                    {},
                ).get(
                    "icon"
                ),
            }
            for sid in pickups
        }

        selected_area = self.config_entry.options.get(
            CONF_PAPIER_KERN,
            GEEN_PAPIER,
        )

        self._handle_paper_schema(
            selected_area,
            streams_from_api,
            pickups,
            streams,
            today,
        )

        data = RWMData(
            streams=streams,
            pickups={
                sid: sorted(pickup_dates)
                for sid, pickup_dates in pickups.items()
                if pickup_dates
            },
            bijgewerkt=now,
            laatste_poging=now,
            bron_status=STATUS_ACTUEEL,
            laatste_fout=None,
        )

        self._validate_data(
            data,
            today,
        )

        self._validate_against_previous(
            data,
            today,
        )

        return data

    async def _load_cache(
        self,
        error: Exception,
        attempt_time: datetime,
    ) -> RWMData | None:
        """Laad en valideer de laatst opgeslagen gegevens."""

        raw_cache = await self._store.async_load()

        if raw_cache is None:
            return None

        try:
            cached_data = RWMData.uit_dict(
                raw_cache
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as cache_error:
            _LOGGER.error(
                "Opgeslagen Wegafval-cache is ongeldig: %s",
                cache_error,
            )
            return None

        cached_data = cached_data.met_fout(
            error,
            attempt_time,
        )

        if cached_data.is_onbruikbaar_verouderd:
            _LOGGER.error(
                "Opgeslagen Wegafval-data is ouder dan "
                "veertien dagen en wordt niet meer gebruikt"
            )
            return None

        return cached_data

    def _schedule_reload_if_streams_changed(
        self,
        previous_stream_ids: set[str],
        current_stream_ids: set[str],
    ) -> None:
        """Herlaad de integratie wanneer afvalstromen wijzigen."""

        if not previous_stream_ids:
            return

        if previous_stream_ids == current_stream_ids:
            return

        if self._reload_scheduled:
            return

        added = sorted(
            current_stream_ids - previous_stream_ids
        )

        removed = sorted(
            previous_stream_ids - current_stream_ids
        )

        _LOGGER.warning(
            "De beschikbare RWM-afvalstromen zijn gewijzigd. "
            "Toegevoegd: %s. Verwijderd: %s. "
            "De integratie wordt opnieuw geladen.",
            added or "geen",
            removed or "geen",
        )

        self._reload_scheduled = True

        self.hass.async_create_task(
            self.hass.config_entries.async_reload(
                self.config_entry.entry_id
            )
        )

    async def _async_update_data(self) -> RWMData:
        """Werk gegevens bij of gebruik geldige opgeslagen data."""

        async with self._update_lock:
            attempt_time = dt_util.utcnow()

            previous_stream_ids = (
                set(self.data.streams)
                if self.data is not None
                else set()
            )

            try:
                data = await self._haal_op()

            except RWMError as error:
                if not self._was_unavailable:
                    _LOGGER.warning(
                        "RWM is niet bereikbaar (%s); de laatst "
                        "bekende geldige gegevens worden gebruikt",
                        error,
                    )

                self._was_unavailable = True

                if self.data is not None:
                    cached_data = self.data.met_fout(
                        error,
                        attempt_time,
                    )

                    if cached_data.is_onbruikbaar_verouderd:
                        raise UpdateFailed(
                            "RWM is niet bereikbaar en de laatst "
                            "bekende gegevens zijn ouder dan "
                            "veertien dagen"
                        ) from error

                    return cached_data

                cached_data = await self._load_cache(
                    error,
                    attempt_time,
                )

                if cached_data is not None:
                    return cached_data

                raise UpdateFailed(
                    "RWM-update mislukt en er is geen geldige "
                    f"cache beschikbaar: {error}"
                ) from error

            if self._was_unavailable:
                _LOGGER.info(
                    "RWM is weer bereikbaar; actuele "
                    "afvalgegevens zijn geladen"
                )

            self._was_unavailable = False

            current_stream_ids = set(
                data.streams
            )

            self._schedule_reload_if_streams_changed(
                previous_stream_ids,
                current_stream_ids,
            )

            try:
                await self._store.async_save(
                    data.als_dict()
                )
            except Exception:
                _LOGGER.exception(
                    "Actuele RWM-data is opgehaald, maar kon "
                    "niet lokaal worden opgeslagen"
                )

            return data
