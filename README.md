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
- Afval buiten zetten (aan als er morgen iets wordt opgehaald)
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

Nieuwe gegevens worden gecontroleerd voordat de bestaande gegevens worden vervangen. Lege, ongeldige of onwaarschijnlijke responses worden geweigerd, bijvoorbeeld wanneer er ineens minder dan de helft van de toekomstige ophaaldatums over is. Blijft dat langer dan 72 uur zo, dan wordt de nieuwe data toch overgenomen.

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

Installeer daarna **Wegafval RWM kalender** en herstart Home Assistant.

Voeg de integratie vervolgens toe via:

```text
Instellingen
→ Apparaten en diensten
→ Integratie toevoegen
→ Wegafval RWM kalender
```

Vul je postcode en huisnummer in.

## Belangrijkste entiteiten

De exacte entity-ID's kunnen per installatie verschillen.

```text
sensor.wegafval_rwm_kalender_volgende_ophaling
sensor.wegafval_rwm_kalender_ophaling_vandaag
sensor.wegafval_rwm_kalender_ophaling_morgen
sensor.wegafval_rwm_kalender_bronstatus
binary_sensor.wegafval_rwm_kalender_afval_buiten_zetten
calendar.wegafval_rwm_kalender
```

Daarnaast worden per beschikbare afvalsoort een datumsensor en een sensor voor het aantal resterende dagen aangemaakt.

Afvalsoorten die tijdelijk geen ophaaldatum hebben (bijvoorbeeld kerstbomen buiten januari) blijven bestaan; hun sensor heeft dan geen waarde.

## Voorbeeld: melding de avond van tevoren

```yaml
automation:
  - alias: "Afval buiten zetten"
    triggers:
      - trigger: time
        at: "19:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.wegafval_rwm_kalender_afval_buiten_zetten
        state: "on"
    actions:
      - action: notify.notify
        data:
          title: "Afval buiten zetten"
          message: >
            Morgen wordt opgehaald:
            {{ state_attr('binary_sensor.wegafval_rwm_kalender_afval_buiten_zetten', 'soorten') | join(', ') }}
```

## Adres wijzigen

Na een verhuizing kun je het adres aanpassen via de drie puntjes bij de integratie → **Opnieuw configureren**. Entiteiten, namen en automations blijven behouden; de opgeslagen gegevens van het oude adres worden verwijderd.

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
→ Wegafval RWM kalender
→ Drie punten
→ Diagnostiek downloaden
```

Adresgegevens (ook de titel van de integratie), postcode, huisnummer en BAG-ID worden daarbij afgeschermd. De gekozen oud-papierkern blijft zichtbaar, omdat die nodig is om problemen met het papierschema te onderzoeken.

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
