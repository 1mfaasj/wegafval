"""Sensoren voor Wegafval RWM kalender."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_ICON, ICONS
from .coordinator import (
    STATUS_ACTUEEL,
    STATUS_CACHE,
    STATUS_VEROUDERD,
    RWMCoordinator,
)
from .entity import RWMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak alle RWM-sensoren aan."""

    coordinator: RWMCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for sid in coordinator.data.streams:
        entities.extend(
            [
                RWMStroomSensor(coordinator, sid),
                RWMDagenSensor(coordinator, sid),
            ]
        )

    entities.extend(
        [
            RWMVolgendeSensor(coordinator),
            RWMDagSensor(
                coordinator,
                0,
                "vandaag",
                "Ophaling vandaag",
            ),
            RWMDagSensor(
                coordinator,
                1,
                "morgen",
                "Ophaling morgen",
            ),
            RWMBronStatusSensor(coordinator),
        ]
    )

    async_add_entities(entities)


def _vandaag() -> date:
    """Geef de lokale datum van Home Assistant."""

    return dt_util.now().date()


class RWMStroomSensor(RWMEntity, SensorEntity):
    """Eerstvolgende ophaaldatum voor één afvalstroom."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator: RWMCoordinator,
        sid: str,
    ) -> None:
        super().__init__(coordinator, sid)

        self._sid = sid

        stream = coordinator.data.streams[sid]

        self._attr_name = stream["title"]
        self._attr_icon = ICONS.get(
            stream.get("icon") or "",
            DEFAULT_ICON,
        )

    @property
    def native_value(self) -> date | None:
        """Geef de eerstvolgende ophaaldatum."""

        return self.coordinator.data.volgende(
            self._sid,
            _vandaag(),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef aanvullende informatie over deze afvalstroom."""

        today = _vandaag()

        upcoming = [
            pickup_date
            for pickup_date in self.coordinator.data.pickups.get(
                self._sid,
                [],
            )
            if pickup_date >= today
        ]

        return {
            "dagen_tot_ophaling": (
                (upcoming[0] - today).days
                if upcoming
                else None
            ),
            "volgende_ophalingen": [
                pickup_date.isoformat()
                for pickup_date in upcoming[:6]
            ],
            "laatst_bijgewerkt": (
                self.coordinator.data.bijgewerkt.isoformat()
            ),
            "bron_status": self.coordinator.data.bron_status,
        }


class RWMDagenSensor(RWMEntity, SensorEntity):
    """Aantal dagen tot de eerstvolgende ophaling."""

    _attr_native_unit_of_measurement = "dagen"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: RWMCoordinator,
        sid: str,
    ) -> None:
        super().__init__(
            coordinator,
            f"{sid}_dagen",
        )

        self._sid = sid
        self._attr_name = (
            f"{coordinator.data.streams[sid]['title']} "
            "dagen tot ophaling"
        )

    @property
    def native_value(self) -> int | None:
        """Geef het aantal dagen tot de volgende ophaling."""

        today = _vandaag()

        next_pickup = self.coordinator.data.volgende(
            self._sid,
            today,
        )

        if next_pickup is None:
            return None

        return (next_pickup - today).days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef de bijbehorende ophaaldatum."""

        next_pickup = self.coordinator.data.volgende(
            self._sid,
            _vandaag(),
        )

        return {
            "datum": (
                next_pickup.isoformat()
                if next_pickup
                else None
            ),
            "bron_status": self.coordinator.data.bron_status,
        }


class RWMVolgendeSensor(RWMEntity, SensorEntity):
    """Welk afval als eerstvolgende wordt opgehaald."""

    _attr_name = "Volgende ophaling"
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(
        self,
        coordinator: RWMCoordinator,
    ) -> None:
        super().__init__(
            coordinator,
            "volgende",
        )

    def _volgende(
        self,
    ) -> tuple[date | None, list[str]]:
        """Bepaal de eerstvolgende datum en afvalstromen."""

        today = _vandaag()

        dates = [
            next_pickup
            for sid in self.coordinator.data.pickups
            if (
                next_pickup
                := self.coordinator.data.volgende(
                    sid,
                    today,
                )
            )
            is not None
        ]

        if not dates:
            return None, []

        first_date = min(dates)

        return (
            first_date,
            self.coordinator.data.op_datum(first_date),
        )

    @property
    def native_value(self) -> str | None:
        """Geef de namen van de eerstvolgende afvalstromen."""

        _, stream_ids = self._volgende()

        value = " + ".join(
            self.coordinator.data.titel(sid)
            for sid in stream_ids
        )

        return value or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef datum en dagen tot de eerstvolgende ophaling."""

        pickup_date, stream_ids = self._volgende()

        return {
            "datum": (
                pickup_date.isoformat()
                if pickup_date
                else None
            ),
            "dagen_tot_ophaling": (
                (pickup_date - _vandaag()).days
                if pickup_date
                else None
            ),
            "soorten": [
                self.coordinator.data.titel(sid)
                for sid in stream_ids
            ],
            "bron_status": self.coordinator.data.bron_status,
        }


class RWMDagSensor(RWMEntity, SensorEntity):
    """Afval dat vandaag of morgen wordt opgehaald."""

    _attr_icon = "mdi:trash-can-outline"

    def __init__(
        self,
        coordinator: RWMCoordinator,
        offset: int,
        sleutel: str,
        naam: str,
    ) -> None:
        super().__init__(
            coordinator,
            sleutel,
        )

        self._offset = offset
        self._attr_name = naam

    def _titels(self) -> list[str]:
        """Geef de afvalstromen op de gekozen dag."""

        pickup_date = _vandaag() + timedelta(
            days=self._offset
        )

        return [
            self.coordinator.data.titel(sid)
            for sid in self.coordinator.data.op_datum(
                pickup_date
            )
        ]

    @property
    def native_value(self) -> str:
        """Geef de afvalstromen of Geen."""

        return ", ".join(self._titels()) or "Geen"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef alle afvalstromen als lijst."""

        return {
            "soorten": self._titels(),
            "bron_status": self.coordinator.data.bron_status,
        }


class RWMBronStatusSensor(RWMEntity, SensorEntity):
    """Status van de RWM-gegevensbron en lokale cache."""

    _attr_name = "Bronstatus"
    _attr_icon = "mdi:database-check"

    def __init__(
        self,
        coordinator: RWMCoordinator,
    ) -> None:
        super().__init__(
            coordinator,
            "bronstatus",
        )

    @property
    def native_value(self) -> str:
        """Geef de huidige status van de gegevensbron."""

        return self.coordinator.data.bron_status

    @property
    def icon(self) -> str:
        """Gebruik een passend icoon voor de huidige status."""

        status = self.coordinator.data.bron_status

        if status == STATUS_ACTUEEL:
            return "mdi:database-check"

        if status == STATUS_CACHE:
            return "mdi:database-clock"

        if status == STATUS_VEROUDERD:
            return "mdi:database-alert"

        return "mdi:database-question"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef diagnostische informatie over de gegevensbron."""

        data = self.coordinator.data

        pickup_count = sum(
            len(pickup_dates)
            for pickup_dates in data.pickups.values()
        )

        future_pickup_count = sum(
            1
            for pickup_dates in data.pickups.values()
            for pickup_date in pickup_dates
            if pickup_date >= _vandaag()
        )

        return {
            "laatste_succesvolle_update": (
                data.bijgewerkt.isoformat()
            ),
            "laatste_poging": (
                data.laatste_poging.isoformat()
            ),
            "cache_leeftijd_uren": (
                data.cache_leeftijd_uren
            ),
            "cache_verouderd": data.is_verouderd,
            "laatste_fout": data.laatste_fout,
            "aantal_afvalstromen": len(data.streams),
            "aantal_ophaaldatums": pickup_count,
            "aantal_toekomstige_ophaaldatums": (
                future_pickup_count
            ),
            "update_interval_uren": 12,
        }
