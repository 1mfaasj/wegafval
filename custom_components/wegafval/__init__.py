"""Wegafval RWM kalender: ophaaldagen rechtstreeks van rwm.nl."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .coordinator import RWMCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]

type RWMConfigEntry = ConfigEntry[RWMCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RWMConfigEntry) -> bool:
    coordinator = RWMCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_opties_gewijzigd))
    return True


async def _opties_gewijzigd(hass: HomeAssistant, entry: RWMConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RWMConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RWMConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
