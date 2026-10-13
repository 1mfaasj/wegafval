"""Sensoren voor RWM Afvalkalender."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_ICON, ICONS
from .coordinator import RWMCoordinator
from .entity import RWMEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: RWMCoordinator = entry.runtime_data
    entiteiten: list[SensorEntity] = []
    for sid in coordinator.data.streams:
        entiteiten += [RWMStroomSensor(coordinator, sid), RWMDagenSensor(coordinator, sid)]
    entiteiten += [
        RWMVolgendeSensor(coordinator),
        RWMDagSensor(coordinator, 0, "vandaag", "Ophaling vandaag"),
        RWMDagSensor(coordinator, 1, "morgen", "Ophaling morgen"),
    ]
    async_add_entities(entiteiten)


def _vandaag() -> date:
    return dt_util.now().date()


class RWMStroomSensor(RWMEntity, SensorEntity):
    """Eerstvolgende ophaaldatum voor één afvalstroom."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: RWMCoordinator, sid: str) -> None:
        super().__init__(coordinator, sid)
        self._sid = sid
        stroom = coordinator.data.streams[sid]
        self._attr_name = stroom["title"]
        self._attr_icon = ICONS.get(stroom.get("icon") or "", DEFAULT_ICON)

    @property
    def native_value(self) -> date | None:
        return self.coordinator.data.volgende(self._sid, _vandaag())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        vandaag = _vandaag()
        komend = [d for d in self.coordinator.data.pickups.get(self._sid, []) if d >= vandaag]
        return {
            "dagen_tot_ophaling": (komend[0] - vandaag).days if komend else None,
            "volgende_ophalingen": [d.isoformat() for d in komend[:6]],
            "laatst_bijgewerkt": self.coordinator.data.bijgewerkt.isoformat(),
        }


class RWMDagenSensor(RWMEntity, SensorEntity):
    """Aantal dagen tot de eerstvolgende ophaling van één afvalstroom (0 = vandaag)."""

    _attr_native_unit_of_measurement = "dagen"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: RWMCoordinator, sid: str) -> None:
        super().__init__(coordinator, f"{sid}_dagen")
        self._sid = sid
        self._attr_name = f"{coordinator.data.streams[sid]['title']} dagen tot ophaling"

    @property
    def native_value(self) -> int | None:
        vandaag = _vandaag()
        volgende = self.coordinator.data.volgende(self._sid, vandaag)
        return (volgende - vandaag).days if volgende else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        volgende = self.coordinator.data.volgende(self._sid, _vandaag())
        return {"datum": volgende.isoformat() if volgende else None}


class RWMVolgendeSensor(RWMEntity, SensorEntity):
    """Welk afval wordt als eerstvolgende opgehaald."""

    _attr_name = "Volgende ophaling"
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator: RWMCoordinator) -> None:
        super().__init__(coordinator, "volgende")

    def _volgende(self) -> tuple[date | None, list[str]]:
        vandaag = _vandaag()
        datums = [
            d
            for sid in self.coordinator.data.pickups
            if (d := self.coordinator.data.volgende(sid, vandaag)) is not None
        ]
        if not datums:
            return None, []
        eerste = min(datums)
        return eerste, self.coordinator.data.op_datum(eerste)

    @property
    def native_value(self) -> str | None:
        _, sids = self._volgende()
        return " + ".join(self.coordinator.data.titel(s) for s in sids) or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        datum, sids = self._volgende()
        return {
            "datum": datum.isoformat() if datum else None,
            "dagen_tot_ophaling": (datum - _vandaag()).days if datum else None,
            "soorten": [self.coordinator.data.titel(s) for s in sids],
        }


class RWMDagSensor(RWMEntity, SensorEntity):
    """Afval dat vandaag of morgen wordt opgehaald ('Geen' als er niets is)."""

    _attr_icon = "mdi:trash-can-outline"

    def __init__(self, coordinator: RWMCoordinator, offset: int, sleutel: str, naam: str) -> None:
        super().__init__(coordinator, sleutel)
        self._offset = offset
        self._attr_name = naam

    def _titels(self) -> list[str]:
        datum = _vandaag() + timedelta(days=self._offset)
        return [self.coordinator.data.titel(s) for s in self.coordinator.data.op_datum(datum)]

    @property
    def native_value(self) -> str:
        return ", ".join(self._titels()) or "Geen"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"soorten": self._titels()}
