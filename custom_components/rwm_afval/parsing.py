"""Parse-logica zonder Home Assistant-afhankelijkheden (los te testen)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
import html
import re
from typing import Any

WEEKDAGEN: dict[str, int] = {
    "maandag": 0,
    "dinsdag": 1,
    "woensdag": 2,
    "donderdag": 3,
    "vrijdag": 4,
    "zaterdag": 5,
    "zondag": 6,
}
_DAG = "|".join(WEEKDAGEN)

# Afvalstroom-id van de infopagina "Oud papier en karton Echt-Susteren"
PAPIER_INFO_ID = "63"


def _datum(waarde: Any) -> date | None:
    try:
        return date.fromisoformat(str(waarde)[:10])
    except (TypeError, ValueError):
        return None


def parse_kalender(items: Any) -> dict[str, set[date]]:
    """Zet /rest/adressen/{bagid}/kalender/{jaar} om naar {afvalstroom_id: {datums}}."""
    resultaat: dict[str, set[date]] = {}
    if not isinstance(items, list):
        return resultaat
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            sid = str(int(item["afvalstroom_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        datum = _datum(item.get("ophaaldatum"))
        if datum is not None:
            resultaat.setdefault(sid, set()).add(datum)
    return resultaat


def parse_stromen(items: Any) -> dict[str, dict[str, Any]]:
    """Zet /rest/adressen/{bagid}/afvalstromen om naar {id: {title, icon, content, next}}."""
    resultaat: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return resultaat
    for item in items:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        sid = str(item["id"])
        titel = item.get("title") or item.get("menu_title") or f"Afvalstroom {sid}"
        resultaat[sid] = {
            "title": str(titel).strip(),
            "icon": item.get("icon"),
            "content": item.get("content") or "",
            "next": _datum(item.get("ophaaldatum")) if item.get("ophaaldatum") else None,
        }
    return resultaat


# --------------------------------------------------------------------------
# Oud papier Echt-Susteren
#
# RWM levert oud papier voor Echt-Susteren niet als kalenderdata, alleen als
# tekst per kern ("1e zaterdag van de maand", "laatste maandag", ...), met
# losse uitzonderingen ("de ophaaldag van 16/02 wordt vervangen door 09/02").
# Die tekst lezen we uit en zetten we om naar concrete datums.
# --------------------------------------------------------------------------

_UITZONDERING = re.compile(
    r"ophaaldag van (\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s+wordt vervangen door\s+"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?",
    re.IGNORECASE,
)

DatumDeel = tuple[int | None, int, int]  # (jaar of None, maand, dag)


def _schoon(fragment: str) -> str:
    tekst = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    tekst = html.unescape(tekst).replace("\xa0", " ")
    return re.sub(r"\s+", " ", tekst).strip()


def _jaar(waarde: str | None) -> int | None:
    if not waarde:
        return None
    jaar = int(waarde)
    return jaar + 2000 if jaar < 100 else jaar


def _parse_regel(tekst: str) -> tuple[int, int, int] | None:
    """Geeft (weekdag, rangorde, dagverschuiving); rangorde -1 = laatste."""
    t = tekst.lower()
    if re.search(r"vrijdag\s+voorafgaand\s+aan\s+de\s+eerste\s+zaterdag", t):
        return (WEEKDAGEN["zaterdag"], 1, -1)
    if m := re.search(rf"\b([1-5])e\s+({_DAG})\b", t):
        return (WEEKDAGEN[m.group(2)], int(m.group(1)), 0)
    if m := re.search(rf"\blaatste\s+({_DAG})\b", t):
        return (WEEKDAGEN[m.group(1)], -1, 0)
    return None


@dataclass
class PapierSchema:
    """Ophaalschema oud papier voor één kern."""

    naam: str
    omschrijving: str
    weekdag: int
    rangorde: int
    dag_verschuiving: int = 0
    uitzonderingen: list[tuple[DatumDeel, DatumDeel]] = field(default_factory=list)

    def _regel_datum(self, jaar: int, maand: int) -> date | None:
        if self.rangorde == -1:
            laatste = date(jaar, maand, calendar.monthrange(jaar, maand)[1])
            datum = laatste - timedelta(days=(laatste.weekday() - self.weekdag) % 7)
        else:
            eerste = date(jaar, maand, 1)
            datum = eerste + timedelta(
                days=(self.weekdag - eerste.weekday()) % 7 + 7 * (self.rangorde - 1)
            )
            if datum.month != maand:
                return None
        return datum + timedelta(days=self.dag_verschuiving)

    def _uitzondering(self, datum: date, huidig_jaar: int) -> date:
        for (vj, vm, vd), (nj, nm, nd) in self.uitzonderingen:
            # Zonder jaartal geldt een uitzondering alleen voor het lopende jaar
            van_jaar = vj or huidig_jaar
            try:
                if datum == date(van_jaar, vm, vd):
                    return date(nj or van_jaar, nm, nd)
            except ValueError:
                continue
        return datum

    def datums(self, jaar: int, huidig_jaar: int) -> list[date]:
        resultaat: set[date] = set()
        for maand in range(1, 13):
            datum = self._regel_datum(jaar, maand)
            if datum is not None:
                resultaat.add(self._uitzondering(datum, huidig_jaar))
        return sorted(resultaat)


def parse_papier_schemas(content: str) -> dict[str, PapierSchema]:
    """Lees de schema's per kern uit de HTML van de oud-papier infopagina."""
    schemas: dict[str, PapierSchema] = {}
    tellers: dict[str, int] = {}
    kop: str | None = None

    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>|<ul\b[^>]*>(.*?)</ul>", content, re.S | re.I):
        if m.group(2) is None:  # een <p>: mogelijke kop (naam van de kern)
            tekst = _schoon(m.group(1))
            if tekst:
                kop = tekst
            continue
        if not kop:
            continue

        items = [
            _schoon(li)
            for li in re.findall(r"<li\b[^>]*>(.*?)</li>", m.group(2), re.S | re.I)
        ]
        items = [i for i in items if i]
        regel, omschrijving = None, ""
        for item in items:
            if regel := _parse_regel(item):
                omschrijving = item
                break
        if regel is None:
            kop = None
            continue

        uitzonderingen: list[tuple[DatumDeel, DatumDeel]] = [
            (
                (_jaar(u.group(3)), int(u.group(2)), int(u.group(1))),
                (_jaar(u.group(6)), int(u.group(5)), int(u.group(4))),
            )
            for u in _UITZONDERING.finditer(" ".join(items))
        ]

        tellers[kop] = tellers.get(kop, 0) + 1
        sleutel = kop if tellers[kop] == 1 else f"{kop} ({tellers[kop]})"
        weekdag, rangorde, verschuiving = regel
        schemas[sleutel] = PapierSchema(
            naam=sleutel,
            omschrijving=omschrijving,
            weekdag=weekdag,
            rangorde=rangorde,
            dag_verschuiving=verschuiving,
            uitzonderingen=uitzonderingen,
        )
        kop = None

    return schemas


def kernen_uit_stromen(stromen: dict[str, dict[str, Any]]) -> dict[str, PapierSchema]:
    """Zoek de oud-papier infopagina voor Echt-Susteren en parse de kernen."""
    stroom = stromen.get(PAPIER_INFO_ID)
    if stroom is None:
        stroom = next(
            (
                s
                for s in stromen.values()
                if "oud papier" in s["title"].lower()
                and "echt-susteren" in s["title"].lower()
            ),
            None,
        )
    if not stroom or not stroom.get("content"):
        return {}
    return parse_papier_schemas(stroom["content"])
