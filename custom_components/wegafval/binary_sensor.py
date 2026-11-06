"""Binaire sensoren voor Wegafval RWM kalender."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import RWMCoordinator
from .entity import RWMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de binaire sensoren aan."""

    coordinator: RWMCoordinator = entry.runtime_data

    async_add_entities(
        [
            RWMBuitenZettenSensor(coordinator),
        ]
    )


class RWMBuitenZettenSensor(RWMEntity, BinarySensorEntity):
    """Aan wanneer er morgen afval wordt opgehaald."""

    _attr_translation_key = "afval_buiten_zetten"
    _object_id_naam = "Afval buiten zetten"

    def __init__(
        self,
        coordinator: RWMCoordinator,
    ) -> None:
        super().__init__(
            coordinator,
            "afval_buiten_zetten",
        )

    def _titels_morgen(self) -> list[str]:
        """Geef de afvalstromen die morgen worden opgehaald."""

        morgen = dt_util.now().date() + timedelta(days=1)
        data = self.coordinator.data

        return [data.titel(sid) for sid in data.op_datum(morgen)]

    @property
    def is_on(self) -> bool:
        """Geef aan of er vanavond afval buiten gezet moet worden."""

        return bool(self._titels_morgen())

    @property
    def icon(self) -> str:
        """Gebruik een passend icoon."""

        return "mdi:delete-alert" if self.is_on else "mdi:delete-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geef de afvalsoorten voor morgen."""

        return {
            "soorten": self._titels_morgen(),
            "datum": (dt_util.now().date() + timedelta(days=1)).isoformat(),
            "bron_status": self.coordinator.data.bron_status,
        }
