"""Tests voor parsing.py (geen Home Assistant nodig).

Uitvoeren: python3 tests/test_parsing.py
"""

from datetime import date
import importlib.util
from pathlib import Path
import sys

# parsing.py los laden (zonder de map op sys.path te zetten, anders botst
# calendar.py van de integratie met de standaardmodule 'calendar')
_PAD = Path(__file__).parent.parent / "custom_components" / "wegafval" / "parsing.py"
_spec = importlib.util.spec_from_file_location("rwm_parsing", _PAD)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["rwm_parsing"] = _mod
_spec.loader.exec_module(_mod)
kernen_uit_stromen = _mod.kernen_uit_stromen
parse_kalender = _mod.parse_kalender
parse_papier_schemas = _mod.parse_papier_schemas
parse_stromen = _mod.parse_stromen

# Ingekorte HTML zoals RWM die levert in afvalstroom 63
PAPIER_HTML = (
    "<h2>Ophaaldagen per kern</h2>\r\n\r\n<p>In Echt-Susteren wordt papier per wijk op een "
    "andere manier opgehaald.&nbsp;</p>\r\n\r\n<p>Echt Centrum</p>\r\n\r\n<p><!-- x-tinymce/html --></p>"
    "\r\n\r\n<ul>\r\n\t<li>1e zaterdag van de maand van 8.30 - 12.00 uur</li>\r\n\t<li>Nieuwe Markt</li>"
    "\r\n</ul>\r\n\r\n<p>Hingen</p>\r\n\r\n<ul>\r\n\t<li>1e zaterdag van de maand van 8.30 -12.00 uur</li>"
    "\r\n</ul>\r\n\r\n<p>Hingen</p>\r\n\r\n<ul>\r\n\t<li><!-- x-tinymce/html -->De vrijdag voorafgaand aan "
    "de eerste zaterdag van de maand van 13.30 - 17.00 uur</li>\r\n</ul>\r\n\r\n<p>Dieteren</p>\r\n\r\n<ul>"
    "\r\n\t<li>2e maandag van de maand</li>\r\n\t<li>Oktober t/m maart vanaf 9.00 uur&nbsp;</li>\r\n</ul>"
    "\r\n\r\n<p>Susteren</p>\r\n\r\n<ul>\r\n\t<li>3e maandag van de maand vanaf 16.00 uur&nbsp;</li>\r\n\t"
    "<li><span style=\"text-decoration-line: underline;\"><strong>Let op: de ophaaldag van 16/02 wordt "
    "vervangen door 09/02</strong></span></li>\r\n</ul>\r\n\r\n<p>Echt-Noord en Echt-Zuid</p>\r\n\r\n<ul>"
    "\r\n\t<li>Laatste zaterdag van de maand van 9.00 - 12.00 uur</li>\r\n\t<li><span><strong>Let op: de "
    "ophaaldag van 26/12/26 wordt vervangen door 02/01/27</strong></span></li>\r\n</ul>\r\n\r\n"
    "<p>Maria Hoop</p>\r\n\r\n<ul>\r\n\t<li>4e zaterdag van de maand van 9.00 - 12.00 uur</li>\r\n</ul>"
)


def test_kalender() -> None:
    data = [
        {"afvalstroom_id": 11, "ophaaldatum": "2026-10-16"},
        {"afvalstroom_id": 22, "ophaaldatum": "2026-10-20"},
        {"afvalstroom_id": 11, "ophaaldatum": "2026-10-30"},
        {"afvalstroom_id": "x", "ophaaldatum": "2026-10-30"},  # ongeldig -> overslaan
        {"afvalstroom_id": 31},  # geen datum -> overslaan
    ]
    res = parse_kalender(data)
    assert res == {"11": {date(2026, 10, 16), date(2026, 10, 30)}, "22": {date(2026, 10, 20)}}
    assert parse_kalender({"error": "x"}) == {}


def test_stromen() -> None:
    res = parse_stromen(
        [
            {"id": 22, "title": "Restafval", "icon": "mini-container", "ophaaldatum": "2026-10-20"},
            {"id": 3, "title": "Accu's", "icon": "x", "ophaaldatum": None},
        ]
    )
    assert res["22"]["next"] == date(2026, 10, 20)
    assert res["3"]["next"] is None


def test_papier() -> None:
    s = parse_papier_schemas(PAPIER_HTML)
    assert list(s) == [
        "Echt Centrum",
        "Hingen",
        "Hingen (2)",
        "Dieteren",
        "Susteren",
        "Echt-Noord en Echt-Zuid",
        "Maria Hoop",
    ], list(s)

    # 1e zaterdag: oktober 2026 -> 3 oktober
    assert date(2026, 10, 3) in s["Echt Centrum"].datums(2026, 2026)
    # Vrijdag vóór 1e zaterdag: 1e zaterdag aug 2026 = 1 aug -> vrijdag 31 juli
    assert date(2026, 7, 31) in s["Hingen (2)"].datums(2026, 2026)
    # 2e maandag okt 2026 = 12 okt
    assert date(2026, 10, 12) in s["Dieteren"].datums(2026, 2026)
    # Uitzondering zonder jaartal: 16/02 -> 09/02 (alleen lopend jaar)
    sus26 = s["Susteren"].datums(2026, 2026)
    assert date(2026, 2, 9) in sus26 and date(2026, 2, 16) not in sus26
    sus27 = s["Susteren"].datums(2027, 2026)
    assert date(2027, 2, 15) in sus27  # 3e maandag feb 2027, geen uitzondering
    # Laatste zaterdag + uitzondering met jaartal naar volgend jaar
    en26 = s["Echt-Noord en Echt-Zuid"].datums(2026, 2026)
    assert date(2026, 12, 26) not in en26 and date(2027, 1, 2) in en26
    assert date(2026, 10, 31) in en26
    # 4e zaterdag okt 2026 = 24 okt
    assert date(2026, 10, 24) in s["Maria Hoop"].datums(2026, 2026)
    # Elke kern: één datum per maand
    for schema in s.values():
        assert len(schema.datums(2026, 2026)) == 12, schema.naam


def test_kernen_uit_stromen() -> None:
    stromen = parse_stromen(
        [{"id": 63, "title": "Oud papier en karton Echt-Susteren", "content": PAPIER_HTML}]
    )
    assert "Echt Centrum" in kernen_uit_stromen(stromen)
    assert kernen_uit_stromen({}) == {}


if __name__ == "__main__":
    for naam, functie in list(globals().items()):
        if naam.startswith("test_"):
            functie()
            print(f"OK  {naam}")
    print("Alle tests geslaagd")
