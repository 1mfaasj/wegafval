# Wegafval

Home Assistant-integratie voor de afvalkalender van **RWM Afval & Reiniging**.

Ondersteunde gemeenten:

- Beek
- Echt-Susteren
- Sittard-Geleen
- Stein

De gegevens worden rechtstreeks opgehaald bij RWM. Er wordt geen externe tussenserver gebruikt.

> Dit is een onafhankelijk project en geen officiële integratie van RWM Afval & Reiniging.

## Functionaliteit

De integratie maakt onder andere entiteiten aan voor:

- De eerstvolgende ophaaldatum per afvalsoort
- Het aantal dagen tot de volgende ophaling
- Ophaling vandaag
- Ophaling morgen
- De eerstvolgende ophaling
- Alle ophalingen in een Home Assistant-kalender
- De status van de RWM-gegevensbron

De gegevens worden tweemaal per dag bijgewerkt.

## Betrouwbaarheid

Wanneer RWM tijdelijk niet bereikbaar is, blijven de laatst bekende geldige gegevens beschikbaar.

De bronstatus kan één van deze waarden hebben:

- `actueel`: de laatste update bij RWM is geslaagd
- `cache`: recente opgeslagen gegevens worden gebruikt
- `verouderd`: de opgeslagen gegevens zijn ouder dan 72 uur

Nieuwe gegevens worden gecontroleerd voordat de bestaande gegevens worden vervangen. Lege, ongeldige of onwaarschijnlijke responses worden geweigerd.

Tijdelijke verbindingsproblemen, rate limits en serverfouten worden automatisch opnieuw geprobeerd.

## Installatie via HACS

Voeg deze repository toe als aangepaste HACS-repository:

```text
https://github.com/1mfaasj/wegafval
```

Selecteer als type:

```text
Integratie
```

Installeer daarna **RWM Afvalkalender** en herstart Home Assistant.

Voeg de integratie vervolgens toe via:

```text
Instellingen
→ Apparaten en diensten
→ Integratie toevoegen
→ RWM Afvalkalender
```

Vul je postcode en huisnummer in.

## Belangrijkste entiteiten

De exacte entity-ID's kunnen per installatie verschillen.

```text
sensor.rwm_afvalkalender_volgende_ophaling
sensor.rwm_afvalkalender_ophaling_vandaag
sensor.rwm_afvalkalender_ophaling_morgen
sensor.rwm_afvalkalender_bronstatus
calendar.rwm_afvalkalender
```

Daarnaast worden per beschikbare afvalsoort een datumsensor en een sensor voor het aantal resterende dagen aangemaakt.

## Bronstatus

De bronstatussensor bevat onder andere:

```text
laatste_succesvolle_update
laatste_poging
cache_leeftijd_uren
cache_verouderd
laatste_fout
aantal_afvalstromen
aantal_ophaaldatums
aantal_toekomstige_ophaaldatums
```

## Oud papier in Echt-Susteren

RWM levert de papierinzameling in Echt-Susteren niet altijd als normale kalendergegevens.

De integratie leest daarom het gepubliceerde schema en rekent dit om naar concrete datums. Eventuele uitzonderingen die RWM vermeldt, worden eveneens verwerkt.

De geselecteerde kern kan achteraf worden gewijzigd via **Configureren** bij de integratie.

## Diagnostiek

Bij problemen kun je via Home Assistant een diagnosebestand downloaden:

```text
Instellingen
→ Apparaten en diensten
→ RWM Afvalkalender
→ Drie punten
→ Diagnostiek downloaden
```

Adresgegevens, postcode, huisnummer en BAG-ID worden daarbij afgeschermd.

Controleer een diagnosebestand altijd voordat je het openbaar deelt.

## Problemen melden

Problemen en verbeteringen kunnen worden gemeld via:

```text
https://github.com/1mfaasj/wegafval/issues
```

Vermeld bij een probleem indien mogelijk:

- Home Assistant-versie
- Versie van Wegafval
- Gemeente
- Bronstatus
- Relevante logmeldingen
- Diagnosebestand
