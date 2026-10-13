"""Client voor de (niet-officiële) API achter rwm.nl/wanneer."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import unquote

import aiohttp
from yarl import URL

from .const import BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 30


class RWMError(Exception):
    """Algemene fout bij het ophalen van RWM-gegevens."""


class RWMConnectionError(RWMError):
    """RWM niet bereikbaar of onverwacht antwoord."""


def normaliseer_postcode(postcode: str) -> str:
    return postcode.replace(" ", "").upper()


class RWMClient:
    """Haalt adres, afvalstromen en kalender op bij rwm.nl."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._xsrf: str | None = None

    async def _start_sessie(self) -> None:
        """Haal sessiecookies op, voor het geval RWM die ooit gaat eisen."""
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self._session.get(
                    f"{BASE_URL}/wanneer", headers={"User-Agent": USER_AGENT}
                ) as resp:
                    await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RWMConnectionError(f"RWM niet bereikbaar: {err}") from err
        cookie = self._session.cookie_jar.filter_cookies(URL(BASE_URL)).get("XSRF-TOKEN")
        self._xsrf = unquote(cookie.value) if cookie else None

    async def _get(self, pad: str, *, mag_404: bool = False) -> Any:
        url = f"{BASE_URL}{pad}"
        for poging in range(2):
            headers = {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/wanneer",
                "X-Requested-With": "XMLHttpRequest",
            }
            if self._xsrf:
                headers["X-XSRF-TOKEN"] = self._xsrf
            try:
                async with asyncio.timeout(TIMEOUT):
                    async with self._session.get(url, headers=headers) as resp:
                        if resp.status == 404 and mag_404:
                            return None
                        if resp.status in (401, 403, 419) and poging == 0:
                            _LOGGER.debug("RWM gaf %s, nieuwe sessie starten", resp.status)
                            await self._start_sessie()
                            continue
                        resp.raise_for_status()
                        return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise RWMConnectionError(f"Fout bij ophalen {pad}: {err}") from err
        raise RWMConnectionError(f"Geen toegang tot {pad}")

    async def zoek_adres(self, postcode: str, huisnummer: int) -> list[dict[str, Any]]:
        data = await self._get(
            f"/adressen/{normaliseer_postcode(postcode)}:{int(huisnummer)}", mag_404=True
        )
        if not isinstance(data, list):
            return []
        return [a for a in data if isinstance(a, dict) and a.get("bagid")]

    async def afvalstromen(self, bagid: str) -> Any:
        return await self._get(f"/rest/adressen/{bagid}/afvalstromen")

    async def kalender(self, bagid: str, jaar: int) -> Any:
        return await self._get(f"/rest/adressen/{bagid}/kalender/{jaar}", mag_404=True)
