# Modelarr School (voorlopige naam)

Een aparte versie van [Modelarr](README.md) voor scholen: leerlingen en medewerkers bewaren en delen hun 3D-modellen in één bibliotheek, en leerlingen kunnen bij een medewerker een print aanvragen. Eén installatie kan meerdere scholen bedienen.

> Deze app is gemaakt met behulp van [Claude](https://claude.ai/) (Anthropic). Dit is een eerste versie.

## Rollen

| Rol | Wat kan het |
|---|---|
| **Beheerder** | Alles: scholen, medewerkers, instellingen, alle modellen |
| **Medewerker** | Ziet alle modellen van de eigen school en de algemene bibliotheek, kan mappen van de algemene bibliotheek verbergen, beheert de leerlingen van de eigen school (aanmaken, CSV-import, nieuw wachtwoord, deactiveren), handelt meldingen en printaanvragen af |
| **Leerling** | Ziet de eigen modellen en alles wat gedeeld is (ook van andere scholen), uploadt in de eigen map, kan delen aan/uit zetten, melden en een print aanvragen |

## Opslag

Alle scholen delen één root folder. Per school en per gebruiker is er een map:

```
<root>/<school>/leerlingen/<leerling>/…
<root>/<school>/medewerkers/<medewerker>/…
<root>/<school>/…                          (gemeenschappelijke schoolbibliotheek)
<root>/<andere map>/…                      (algemene bibliotheek: zichtbaar voor alle leerlingen)
<root>/<school>/.aanvragen/<id>/…          (gesliced bestand bij een printaanvraag, verborgen)
```

Modellen buiten de schoolmappen vormen de **algemene bibliotheek**: ze zijn voor iedereen zichtbaar. Een medewerker of beheerder kan onder **Mappen** een map (met alles daarin) verbergen voor leerlingen. De eigenaar van een model in een schoolmap volgt uit de map waarin het staat. Delen aan of uit is alleen een vinkje in de database: er worden geen bestanden verplaatst. Of een nieuw model van een leerling standaard gedeeld wordt, stel je in:

- **Instellingen → Algemeen → Uploads van leerlingen**: de algemene keuze, standaard aan.
- **Instellingen → Scholen → Uploads delen**: per school *Algemeen* (volgt de algemene keuze), *Standaard aan* of *Standaard uit*.

Een leerling kan delen bij het uploaden en per model nog aan- of uitzetten. De instelling geldt ook voor bestanden die rechtstreeks in de map van een leerling worden gezet, bijvoorbeeld via de share. Bestaande modellen veranderen niet als je de instelling wijzigt. Modellen van medewerkers zijn standaard gedeeld.

## Installeren

Hetzelfde als Modelarr (zie [README.md](README.md)). Daarna:

1. Voeg onder **Instellingen → Mediabeheer** de gezamenlijke root folder toe en zet *verplaatsen/verwijderen* aan (nodig om eigen modellen te kunnen verwijderen).
2. Maak onder **Instellingen → Scholen** per school een school aan, kies de root folder en eventueel een eigen limiet per leerling (MB).
3. Maak onder **Instellingen → Gebruikers** de medewerkers aan (rol *Medewerker*, kies de school).
4. Medewerkers maken zelf leerlingen aan onder **Leerlingen**, één voor één of met een CSV.

Staat de root folder op een NAS-share? Volg dan ook "Share na een herstart" in [README.md](README.md). Is de share niet bereikbaar of onverwacht leeg, dan ziet de beheerder bovenaan een rode balk met het pad. Leerlingen en medewerkers zien alleen een algemene melding, zonder paden van de server. Er wordt in dat geval niets uit de bibliotheek verwijderd.

### CSV-import van leerlingen

Eerste regel met kolomnamen (`;` of `,`): `naam`, `klas`, optioneel `gebruikersnaam`, `wachtwoord`, `email`. Alleen `naam` is genoeg: de gebruikersnaam wordt dan afgeleid van de naam en het wachtwoord wordt aangemaakt. Na de import zie je de wachtwoorden één keer, met een knop om ze als CSV te downloaden of af te drukken.

**Nieuw schooljaar: klassen bijwerken.** Importeer het bestand opnieuw met `gebruikersnaam` (of `email`) en `klas`. Leerlingen die al bestaan in jouw school worden bijgewerkt (klas, en de naam als die in het bestand staat) en krijgen géén nieuw wachtwoord; nieuwe leerlingen worden aangemaakt. Op alleen een naam wordt niet gekoppeld, omdat twee leerlingen dezelfde naam kunnen hebben. Een gebruikersnaam van een andere school wordt niet aangeraakt. Je ziet vooraf hoeveel leerlingen worden aangemaakt en bijgewerkt. Een klas kun je ook per leerling aanpassen op de pagina Leerlingen.

## Privacy

- Een leerling ziet bij andermans model, van de eigen school, alleen de **voornaam**; bij een model van een andere school alleen de **schoolnaam**.
- Medewerkers van de eigen school zien de volledige naam en de klas.
- Leerlingen zien geen paden op de schijf, geen gebruikerslijst en geen beheerpagina's.
- Modellen kunnen **gemeld** worden. Een medewerker van de school van het model kan de melding negeren, het model verbergen of verwijderen.
- Het gaat om gegevens van minderjarigen. Overleg met de functionaris gegevensbescherming over verwerkersovereenkomst, bewaartermijnen en een DPIA.

## Printaanvragen

1. De leerling opent een model en kiest **Print aanvragen**: kleur(en) (maximaal 4), aantal en een opmerking.
2. De medewerker van de school van de leerling ziet de aanvraag onder **Printaanvragen**, slicet het model zelf en legt het gesliced bestand (`.3mf`, `.gcode`, `.bgcode`) bij de aanvraag. De status wordt dan *Bezig*.
3. De medewerker zet de aanvraag op *Klaar* (met een bericht, bijvoorbeeld waar de print ligt) of *Afgewezen*.
4. De leerling ziet de status. Zolang een aanvraag *Open* is kan de leerling hem intrekken.

## Inloggen met Microsoft (Entra ID)

Leerlingen en medewerkers loggen in met hun schoolaccount; er hoeven geen wachtwoorden meer uitgedeeld te worden. Rol en school volgen uit de **beveiligingsgroepen** in Microsoft.

1. Maak in het Entra-beheercentrum een **App-registratie** (alleen deze tenant, type *Web*). Voeg als omleidings-URL toe: `https://<jouw-adres>/api/ms/callback` (staat ook op de instellingenpagina). Microsoft eist https, behalve voor `localhost`.
2. Geef de app het API-recht **User.Read** (delegated) en maak een **clientgeheim** aan.
3. Zet bij *Token configuration* een **groepsclaim** aan (*Security groups*). Heeft iemand meer dan 200 groepen, dan haalt Modelarr de lijst zelf op bij Graph.
4. Open in Modelarr **Instellingen → Microsoft**: vul Tenant-ID, Client-ID en het geheim in, en eventueel het groep-ID van de beheerders.
5. Vul bij **Instellingen → Scholen** per school het groep-ID van de leerlingen en van de medewerkers in.
6. Zet *Inloggen met Microsoft* aan. Op de inlogpagina staat nu een Microsoft-knop.

De **klas** van een leerling wordt bij elke login overgenomen uit het veld *Afdeling* (Department) van het Microsoft-account (aan/uit onder Instellingen → Microsoft). Is het veld leeg, dan blijft de bestaande klas staan. Een medewerker met een andere klas dan Microsoft opgeeft, ziet dus bij de volgende login de Microsoft-waarde.

Wie inlogt krijgt de rol van de **hoogste** groep: beheerders, dan medewerkers van een school, dan leerlingen van een school. Iemand zonder bekende groep komt er niet in. Een account wordt bij de eerste keer aangemaakt (met eigen map), een bestaand lokaal account met dezelfde inlognaam of hetzelfde e-mailadres wordt gekoppeld. Bij elke login wordt rol en school opnieuw uit de groepen bepaald: een leerling die van school wisselt, verhuist mee. Een lokale beheerder verliest zijn rechten niet door de koppeling.

*Alleen Microsoft* verbergt het wachtwoordformulier en weigert wachtwoordinlog van iedereen behalve lokale beheerders (zonder Microsoft-koppeling). Zij loggen in via `https://<jouw-adres>/?lokaal=1`. Maak dus altijd eerst een lokaal beheerdersaccount aan.

### De app alleen voor de juiste mensen beschikbaar maken

Standaard kan iedereen in de tenant zich bij een app aanmelden. Beperk dat in de **Enterprise-applicatie** (Entra-beheercentrum → Enterprise-applicaties → jouw app):

1. Open **Eigenschappen** en zet **Toewijzing vereist? (Assignment required)** op *Ja*. Wie niet is toegewezen, krijgt van Microsoft een foutmelding (AADSTS50105) en komt Modelarr niet in.
2. Open **Gebruikers en groepen → Gebruiker/groep toevoegen** en voeg de **groepen** toe die mogen inloggen: de leerlingengroep en de medewerkersgroep van elke school, en de beheerdersgroep. Voeg dus groepen toe en geen losse gebruikers; nieuwe leden van een groep krijgen dan vanzelf toegang. (Voor groepen als toewijzing is een Entra ID P1-licentie nodig, die in onderwijstenants meestal aanwezig is.)
3. Zorg dat dezelfde groepen zijn ingevuld in Modelarr (Instellingen → Scholen en Microsoft). Modelarr weigert op zijn beurt iedereen die in geen van die groepen zit.

Zo zijn er twee sloten: Microsoft laat alleen toegewezen groepen toe, en Modelarr bepaalt daarna rol en school uit dezelfde groepen.

### Eerste keer inloggen van een nieuwe gebruiker

Bij de allereerste login van een nieuwe gebruiker kan een foutmelding verschijnen. Vernieuw dan de pagina (F5) of klik opnieuw op *Inloggen met Microsoft*: de tweede keer werkt het wel, en daarna blijft het werken. Het account is bij de eerste poging al aangemaakt. Zeg dit tegen nieuwe gebruikers. Komt de melding bij iedereen elke keer terug, controleer dan of de persoon in de juiste groep zit en of die groep aan de Enterprise-applicatie is toegewezen.

Achter een reverse proxy: vul bij *Publiek adres* het https-adres in dat gebruikers zien, anders klopt de omleidings-URL niet.

## Melding voor medewerkers

Modelarr verstuurt geen e-mail. In plaats daarvan krijgt een medewerker (en een beheerder) een pop-up rechtsonder in beeld zodra er printaanvragen of meldingen openstaan: direct na het inloggen, en daarna opnieuw als er nieuwe bijkomen. Met een knop ga je naar de aanvragen of de meldingen; *Niet nu* sluit de pop-up tot er weer iets nieuws is. Bij een medewerker telt alleen de eigen school. De pop-up verschijnt alleen zolang Modelarr open staat in de browser.

## Leerlingen verwijderen

Op de pagina Leerlingen: een prullenbak-knop per leerling, selectievakjes met "Verwijder geselecteerde" (bijvoorbeeld een hele klas, filter eerst op klas) en "Verwijder alle gedeactiveerde leerlingen" (zet eerst Actief uit bij wie weg moet, of na de CSV-import van een nieuw schooljaar).

- **Standaard blijven de bestanden bewaard.** Het account verdwijnt; de map en de modellen blijven in de bibliotheek staan, zonder eigenaar en niet meer gedeeld (alleen medewerkers en beheerders zien ze).
- **Met het vinkje "Ook alle bestanden verwijderen"** gaat de map van de leerling naar `<root>/.prullenbak` en verdwijnen de modellen uit de bibliotheek. Je kunt de map daar zelf terugzetten of definitief wissen.
- Open printaanvragen van de leerling worden geannuleerd; afgehandelde aanvragen en meldingen blijven staan (afzender: "Verwijderde leerling").
- Een medewerker verwijdert alleen leerlingen van de eigen school; de beheerder kiest eerst een school.
- Microsoft-leerlingen: haal ze ook uit de groep in Entra, anders wordt het account bij de volgende inlog opnieuw (leeg) aangemaakt.

## Nog niet gebouwd

- Bambuddy per school en beperking van de kleurkeuze tot de aanwezige filamenten
- Per-school beheer van medewerkers door een medewerker
- Hetzelfde voor de gewone Modelarr (alleen de school-versie heeft nu Microsoft-login)
