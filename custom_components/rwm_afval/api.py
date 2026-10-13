"""Client voor de niet-officiële API achter rwm.nl/wanneer."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from urllib.parse import unquote

import aiohttp
from yarl import URL

from .const import BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3
MAX_RESPONSE_SIZE = 5_000_000

RETRY_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

SESSION_STATUS_CODES = {
    401,
    403,
    419,
}


class RWMError(Exception):
    """Algemene fout bij het ophalen van RWM-gegevens."""


class RWMConnectionError(RWMError):
    """RWM is niet bereikbaar."""


class RWMTimeoutError(RWMConnectionError):
    """Het verzoek naar RWM duurde te lang."""


class RWMHTTPError(RWMConnectionError):
    """RWM gaf een onverwachte HTTP-status terug."""

    def __init__(self, status: int, pad: str) -> None:
        self.status = status
        self.pad = pad
        super().__init__(f"RWM gaf HTTP-status {status} voor {pad}")


class RWMRateLimitError(RWMHTTPError):
    """RWM heeft tijdelijk te veel verzoeken ontvangen."""


class RWMAccessError(RWMHTTPError):
    """RWM heeft het verzoek geweigerd."""


class RWMResponseError(RWMError):
    """RWM gaf een ongeldige of onverwachte response terug."""


def normaliseer_postcode(postcode: str) -> str:
    """Normaliseer een Nederlandse postcode."""

    return postcode.replace(" ", "").upper()


class RWMClient:
    """Haalt adres, afvalstromen en kalender op bij rwm.nl."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._xsrf: str | None = None
        self._session_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        """Bouw de headers voor een RWM-verzoek."""

        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "Referer": f"{BASE_URL}/wanneer",
            "X-Requested-With": "XMLHttpRequest",
        }

        if self._xsrf:
            headers["X-XSRF-TOKEN"] = self._xsrf

        return headers

    async def _start_sessie(self) -> None:
        """Haal sessiecookies en een eventueel XSRF-token op."""

        async with self._session_lock:
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with self._session.get(
                        f"{BASE_URL}/wanneer",
                        headers={"User-Agent": USER_AGENT},
                    ) as response:
                        if response.status >= 400:
                            raise RWMHTTPError(
                                response.status,
                                "/wanneer",
                            )

                        await response.read()

            except TimeoutError as err:
                raise RWMTimeoutError(
                    "Time-out bij het starten van de RWM-sessie"
                ) from err

            except aiohttp.ClientError as err:
                raise RWMConnectionError(
                    f"RWM-sessie kon niet worden gestart: {err}"
                ) from err

            cookie = self._session.cookie_jar.filter_cookies(
                URL(BASE_URL)
            ).get("XSRF-TOKEN")

            self._xsrf = unquote(cookie.value) if cookie else None

    @staticmethod
    def _retry_delay(
        attempt: int,
        retry_after: str | None,
    ) -> float:
        """Bereken de wachttijd voor een volgende poging."""

        if retry_after:
            try:
                return min(max(float(retry_after), 1.0), 300.0)
            except ValueError:
                pass

        base_delay = 2 ** attempt
        jitter = random.uniform(0.25, 1.0)

        return min(base_delay + jitter, 30.0)

    async def _read_json(
        self,
        response: aiohttp.ClientResponse,
        path: str,
    ) -> Any:
        """Lees en valideer een JSON-response."""

        content_length = response.content_length

        if (
            content_length is not None
            and content_length > MAX_RESPONSE_SIZE
        ):
            raise RWMResponseError(
                f"Response voor {path} is onverwacht groot: "
                f"{content_length} bytes"
            )

        try:
            raw = await response.read()
        except aiohttp.ClientError as err:
            raise RWMConnectionError(
                f"Response voor {path} kon niet worden gelezen: {err}"
            ) from err

        if len(raw) > MAX_RESPONSE_SIZE:
            raise RWMResponseError(
                f"Response voor {path} is onverwacht groot: "
                f"{len(raw)} bytes"
            )

        if not raw.strip():
            raise RWMResponseError(
                f"RWM gaf een lege response voor {path}"
            )

        try:
            return await response.json(
                content_type=None,
                encoding="utf-8",
            )
        except (
            aiohttp.ContentTypeError,
            UnicodeDecodeError,
            ValueError,
        ) as err:
            content_type = response.headers.get(
                "Content-Type",
                "onbekend",
            )

            raise RWMResponseError(
                f"RWM gaf geen geldige JSON voor {path}; "
                f"Content-Type: {content_type}"
            ) from err

    async def _get(
        self,
        path: str,
        *,
        allow_404: bool = False,
    ) -> Any:
        """Voer een GET-verzoek uit met beperkte retries."""

        url = f"{BASE_URL}{path}"
        session_refreshed = False
        last_error: RWMError | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with self._session.get(
                        url,
                        headers=self._headers(),
                    ) as response:
                        if response.status == 404 and allow_404:
                            return None

                        if response.status in SESSION_STATUS_CODES:
                            if not session_refreshed:
                                session_refreshed = True

                                _LOGGER.debug(
                                    "RWM gaf HTTP %s voor %s; "
                                    "nieuwe sessie starten",
                                    response.status,
                                    path,
                                )

                                await self._start_sessie()
                                continue

                            raise RWMAccessError(
                                response.status,
                                path,
                            )

                        if response.status in RETRY_STATUS_CODES:
                            if response.status == 429:
                                last_error = RWMRateLimitError(
                                    response.status,
                                    path,
                                )
                            else:
                                last_error = RWMHTTPError(
                                    response.status,
                                    path,
                                )

                            if attempt + 1 >= MAX_ATTEMPTS:
                                raise last_error

                            delay = self._retry_delay(
                                attempt,
                                response.headers.get("Retry-After"),
                            )

                            _LOGGER.warning(
                                "RWM gaf HTTP %s voor %s; "
                                "nieuwe poging over %.1f seconden",
                                response.status,
                                path,
                                delay,
                            )

                            await asyncio.sleep(delay)
                            continue

                        if response.status >= 400:
                            raise RWMHTTPError(
                                response.status,
                                path,
                            )

                        return await self._read_json(
                            response,
                            path,
                        )

            except TimeoutError as err:
                last_error = RWMTimeoutError(
                    f"Time-out bij ophalen van {path}"
                )

                if attempt + 1 >= MAX_ATTEMPTS:
                    raise last_error from err

                delay = self._retry_delay(attempt, None)

                _LOGGER.warning(
                    "Time-out bij ophalen van %s; "
                    "nieuwe poging over %.1f seconden",
                    path,
                    delay,
                )

                await asyncio.sleep(delay)

            except aiohttp.ClientError as err:
                last_error = RWMConnectionError(
                    f"Netwerkfout bij ophalen van {path}: {err}"
                )

                if attempt + 1 >= MAX_ATTEMPTS:
                    raise last_error from err

                delay = self._retry_delay(attempt, None)

                _LOGGER.warning(
                    "Netwerkfout bij ophalen van %s; "
                    "nieuwe poging over %.1f seconden",
                    path,
                    delay,
                )

                await asyncio.sleep(delay)

        if last_error is not None:
            raise last_error

        raise RWMConnectionError(
            f"Ophalen van {path} is mislukt"
        )

    async def zoek_adres(
        self,
        postcode: tr,
        huisnummer: int,
    ) -> list[dict[str, Any]]:
        """Zoek adressen op postcode en huisnummer."""

        postcode = normaliseer_postcode(postcode)

        data = await self._get(
            f"/adressen/{postcode}:{int(huisnummer)}",
            allow_404=True,
        )

        if data is None:
            return []

        if not isinstance(data, list):
            raise RWMResponseError(
                "RWM gaf een onverwachte adresresponse terug"
            )

        return [
            address
            for address in data
            if isinstance(address, dict)
            and address.get("bagid")
        ]

    async def afvalstromen(
        self,
        bagid: str,
    ) -> list[dict[str, Any]]:
        """Haal de afvalstromen voor een BAG-ID op."""

        data = await self._get(
            f"/rest/adressen/{bagid}/afvalstromen"
        )

        if not isinstance(data, list):
            raise RWMResponseError(
                "RWM gaf een onverwachte afvalstromenresponse terug"
            )

        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    async def kalender(
        self,
        bagid: str,
        jaar: int,
    ) -> list[dict[str, Any]] | None:
        """Haal de afvalkalender voor een BAG-ID en jaar op."""

        data = await self._get(
            f"/rest/adressen/{bagid}/kalender/{int(jaar)}",
            allow_404=True,
        )

        if data is None:
            return None

        if not isinstance(data, list):
            raise RWMResponseError(
                f"RWM gaf een onverwachte kalenderresponse "
                f"voor {jaar} terug"
            )

        return [
            item
            for item in data
            if isinstance(item, dict)
        ]