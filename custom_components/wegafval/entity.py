"""Basis-entiteit voor Wegafval RWM kalender."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADRES, CONF_BAGID, DOMAIN
from .coordinator import RWMCoordinator


class RWMEntity(CoordinatorEntity[RWMCoordinator]):
    """Gedeelde basis: apparaatinfo en verversen rond middernacht."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RWMCoordinator, sleutel: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        bagid = entry.data[CONF_BAGID]
        self._attr_unique_id = f"{bagid}_{sleutel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bagid)},
            name="Wegafval RWM kalender",
            manufacturer="RWM afval & reiniging",
            model=entry.data.get(CONF_ADRES, entry.title),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://rwm.nl/wanneer",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # 'Vandaag', 'morgen' en 'dagen tot' veranderen om middernacht, ook zonder nieuwe data
        self.async_on_remove(
            async_track_time_change(self.hass, self._middernacht, hour=0, minute=0, second=5)
        )

    @callback
    def _middernacht(self, _now: datetime) -> None:
        self.async_write_ha_state()
