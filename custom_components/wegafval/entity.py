"""Basisentiteit voor Wegafval RWM kalender."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    DeviceEntryType,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADRES, CONF_BAGID, DOMAIN
from .coordinator import RWMCoordinator


class RWMEntity(CoordinatorEntity[RWMCoordinator]):
    """Gedeelde basis voor Wegafval-entiteiten."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RWMCoordinator,
        sleutel: str,
    ) -> None:
        super().__init__(coordinator)

        entry = coordinator.config_entry
        bagid = entry.data[CONF_BAGID]

        self._attr_unique_id = f"{bagid}_{sleutel}"

        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    bagid,
                )
            },
            name="Wegafval RWM kalender",
            manufacturer="RWM afval & reiniging",
            model=entry.data.get(
                CONF_ADRES,
                entry.title,
            ),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://rwm.nl/wanneer",
        )

    # Basis voor de entity-ID bij het eerste aanmaken. Namen komen uit de
    # vertalingen, maar Home Assistant baseert nieuwe entity-ID's op de Engelse
    # naam; zo blijven de ID's Nederlands, zoals in eerdere versies.
    _object_id_naam: str | None = None

    @property
    def suggested_object_id(self) -> str | None:
        """Geef de Nederlandstalige basis voor de entity-ID."""

        if self._object_id_naam is not None:
            return self._object_id_naam

        return super().suggested_object_id
