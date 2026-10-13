"""Knoppen voor Wegafval RWM kalender."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MANUAL_REFRESH_INTERVAL
from .coordinator import RWMCoordinator
from .entity import RWMEntity

_LOGGER = logging.getLogger(__name__)


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
        """Initialiseer de vernieuwknop."""

        super().__init__(
            coordinator,
            "nu_bijwerken",
        )

    async def async_press(self) -> None:
        """Start een handmatige update."""

        data = self.coordinator.data

        if data is not None:
            elapsed = dt_util.utcnow() - data.laatste_poging

            if elapsed < MANUAL_REFRESH_INTERVAL:
                remaining = MANUAL_REFRESH_INTERVAL - elapsed

                _LOGGER.info(
                    "Handmatig bijwerken overgeslagen; "
                    "probeer het over ongeveer %s seconden opnieuw",
                    max(
                        1,
                        round(remaining.total_seconds()),
                    ),
                )

                return

        _LOGGER.info(
            "Handmatige update van de RWM-afvalkalender gestart"
        )

        await self.coordinator.async_request_refresh()