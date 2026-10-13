"""Knoppen voor Wegafval RWM kalender."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MANUAL_REFRESH_INTERVAL
from .coordinator import RWMCoordinator
from .entity import RWMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de handmatige vernieuwknop aan."""

    coordinator: RWMCoordinator = entry.runtime_data

    async_add_entities(
        [
            RWMRefreshButton(coordinator),
        ]
    )


class RWMRefreshButton(RWMEntity, ButtonEntity):
    """Vernieuw de RWM-afvalgegevens handmatig."""

    _attr_translation_key = "nu_bijwerken"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: RWMCoordinator,
    ) -> None:
        super().__init__(
            coordinator,
            "nu_bijwerken",
        )

    @property
    def available(self) -> bool:
        """Geef aan of handmatig vernieuwen is toegestaan."""

        if not super().available:
            return False

        data = self.coordinator.data

        if data is None:
            return True

        elapsed = dt_util.utcnow() - data.laatste_poging

        return elapsed >= MANUAL_REFRESH_INTERVAL

    async def async_press(self) -> None:
        """Start een handmatige update."""

        await self.coordinator.async_request_refresh()