"""Kalender-entiteit voor Wegafval RWM kalender."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import RWMCoordinator
from .entity import RWMEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RWMKalender(entry.runtime_data)])


class RWMKalender(RWMEntity, CalendarEntity):
    """Alle ophaaldagen als hele-dag-afspraken."""

    _attr_name = None  # gebruikt de apparaatnaam: calendar.wegafvalkalender

    def __init__(self, coordinator: RWMCoordinator) -> None:
        super().__init__(coordinator, "kalender")

    def _afspraken(self) -> Iterator[CalendarEvent]:
        data = self.coordinator.data
        for sid, datums in data.pickups.items():
            for d in datums:
                yield CalendarEvent(
                    start=d,
                    end=d + timedelta(days=1),
                    summary=data.titel(sid),
                    uid=f"{sid}_{d.isoformat()}",
                )

    @property
    def event(self) -> CalendarEvent | None:
        vandaag = dt_util.now().date()
        komend = [a for a in self._afspraken() if a.start >= vandaag]
        return min(komend, key=lambda a: (a.start, a.summary), default=None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return sorted(
            (
                a
                for a in self._afspraken()
                if dt_util.start_of_local_day(a.start) < end_date
                and dt_util.start_of_local_day(a.end) > start_date
            ),
            key=lambda a: (a.start, a.summary),
        )
