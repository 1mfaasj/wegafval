"""Constanten voor Wegafval RWM kalender."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "wegafval"

BASE_URL: Final = "https://rwm.nl"

USER_AGENT: Final = (
    "HomeAssistant-Wegafval "
    "(https://github.com/1mfaasj/wegafval)"
)

CONF_POSTCODE: Final = "postcode"
CONF_HUISNUMMER: Final = "huisnummer"
CONF_TOEVOEGING: Final = "toevoeging"
CONF_BAGID: Final = "bagid"
CONF_ADRES: Final = "adres"
CONF_PAPIER_KERN: Final = "papier_kern"

GEEN_PAPIER: Final = "geen"

PAPIER_STREAM_ID: Final = "papier"

UPDATE_INTERVAL: Final = timedelta(hours=12)

CACHE_WARNING_AGE: Final = timedelta(hours=72)
CACHE_MAXIMUM_AGE: Final = timedelta(days=14)

MANUAL_REFRESH_INTERVAL: Final = timedelta(minutes=5)

STORAGE_VERSION: Final = 2

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