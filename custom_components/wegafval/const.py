"""Constanten voor de Wegafval RWM kalender integratie."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "wegafval"

BASE_URL: Final = "https://rwm.nl"
USER_AGENT: Final = (
    "HomeAssistant-RWM-Afvalkalender (+https://www.home-assistant.io)"
)

CONF_POSTCODE: Final = "postcode"
CONF_HUISNUMMER: Final = "huisnummer"
CONF_TOEVOEGING: Final = "toevoeging"
CONF_BAGID: Final = "bagid"
CONF_ADRES: Final = "adres"
CONF_PAPIER_KERN: Final = "papier_kern"
GEEN_PAPIER: Final = "geen"

# Interne sleutel voor het berekende oud-papierschema (Echt-Susteren)
PAPIER_STREAM_ID: Final = "papier"

# Twee keer per dag verversen: genoeg voor wijzigingen, zonder RWM te belasten
UPDATE_INTERVAL: Final = timedelta(hours=12)

STORAGE_VERSION: Final = 1

# RWM-icoonnaam -> Material Design Icon
ICONS: Final[dict[str, str]] = {
    "mini-container": "mdi:trash-can",
    "gft": "mdi:leaf",
    "plastic": "mdi:recycle",
    "kerstboom": "mdi:pine-tree",
    "snoeiafval": "mdi:tree",
    "papieren-doos": "mdi:package-variant",
    "textiel": "mdi:tshirt-crew",
    "glas-gekleurd": "mdi:bottle-wine",
    "elektronisch-apparaat": "mdi:television",
    "kca-algemeen": "mdi:flask",
}
DEFAULT_ICON: Final = "mdi:delete-empty"
