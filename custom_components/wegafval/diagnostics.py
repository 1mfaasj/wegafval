"""Diagnostiek voor de Wegafval RWM kalender-integratie."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ADRES,
    CONF_BAGID,
    CONF_HUISNUMMER,
    CONF_POSTCODE,
    CONF_TOEVOEGING,
)
from .coordinator import RWMCoordinator

TO_REDACT = {
    CONF_ADRES,
    CONF_BAGID,
    CONF_HUISNUMMER,
    CONF_POSTCODE,
    CONF_TOEVOEGING,
}


def _future_pickups(
    coordinator: RWMCoordinator,
    today: date,
) -> dict[str, list[str]]:
    """Geef toekomstige datums per afvalstroom."""

    return {
        sid: [
            pickup_date.isoformat()
            for pickup_date in pickup_dates
            if pickup_date >= today
        ]
        for sid, pickup_dates in coordinator.data.pickups.items()
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry,
) -> dict[str, Any]:
    """Geef veilige diagnostische informatie terug."""

    coordinator: RWMCoordinator = entry.runtime_data
    data = coordinator.data
    today = dt_util.now().date()

    pickup_count = sum(
        len(pickup_dates)
        for pickup_dates in data.pickups.values()
    )

    future_pickup_count = sum(
        1
        for pickup_dates in data.pickups.values()
        for pickup_date in pickup_dates
        if pickup_date >= today
    )

    stream_details = {
        sid: {
            "title": stream.get("title"),
            "icon": stream.get("icon"),
            "pickup_count": len(
                data.pickups.get(sid, [])
            ),
            "future_pickup_count": len(
                [
                    pickup_date
                    for pickup_date in data.pickups.get(sid, [])
                    if pickup_date >= today
                ]
            ),
            "next_pickup": (
                next_pickup.isoformat()
                if (
                    next_pickup
                    := data.volgende(sid, today)
                )
                else None
            ),
        }
        for sid, stream in data.streams.items()
    }

    return {
        "config_entry": {
            "title": entry.title,
            "data": async_redact_data(
                dict(entry.data),
                TO_REDACT,
            ),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": (
                coordinator.last_update_success
            ),
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "source_status": {
            "status": data.bron_status,
            "last_successful_update": (
                data.bijgewerkt.isoformat()
            ),
            "last_attempt": (
                data.laatste_poging.isoformat()
            ),
            "cache_age_hours": (
                data.cache_leeftijd_uren
            ),
            "cache_is_stale": data.is_verouderd,
            "last_error": data.laatste_fout,
        },
        "statistics": {
            "stream_count": len(data.streams),
            "pickup_count": pickup_count,
            "future_pickup_count": future_pickup_count,
        },
        "streams": stream_details,
        "future_pickups": _future_pickups(
            coordinator,
            today,
        ),
    }