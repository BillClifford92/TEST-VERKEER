# Files-feed uit NDW open data

Deze repository zet elke 10 minuten de open data van NDW (`actueel_beeld.xml.gz`, DATEX II v3) om naar een RSS-feed met actuele files. Die feed kan een canvas app lezen met de standaard RSS-connector, zonder premiumlicentie.

```
NDW open data ──(GitHub Action, elke 10 min)──> docs/feed.xml ──(GitHub Pages)──> RSS.ListFeedItems() in Power Apps
```

## Eenmalig instellen

1. **Repository aanmaken.** Maak op github.com een nieuwe repository, bijvoorbeeld `files-feed`, en zet hem op **Public**. GitHub Pages is alleen gratis voor publieke repositories. Dat is hier geen probleem, want de data is al openbaar.
2. **Bestanden uploaden.** Kies *Add file → Upload files* en sleep alle bestanden uit deze map erin, inclusief de map `.github/workflows` en de map `docs`. Mappen die met een punt beginnen zijn soms verborgen. Lukt het slepen niet, maak het bestand dan aan via *Add file → Create new file* met als naam `.github/workflows/feed.yml` en plak de inhoud erin.
3. **Schrijfrechten voor de Action.** Ga naar *Settings → Actions → General → Workflow permissions*, kies **Read and write permissions** en sla op.
4. **Filters aanpassen** in `.github/workflows/feed.yml`:
   - `WEGEN`: wegnummers die je wilt zien, of leeg voor alle wegen.
   - `BBOX`: het gebied als `minLon,minLat,maxLon,maxLat`, of leeg voor heel Nederland.
   - `TYPES`: `AbnormalTraffic` geeft alleen files. Voeg `Accident,VehicleObstruction` toe als je ook ongevallen en pech wilt zien.
5. **Eerste run.** Ga naar het tabblad *Actions → Files-feed bijwerken → Run workflow*. Na ongeveer een minuut staan `docs/feed.xml` en `docs/debug.txt` in de repository.
6. **Pages aanzetten.** Ga naar *Settings → Pages → Build and deployment*, kies Source: *Deploy from a branch*, Branch: `main`, map `/docs`, en sla op. Na een paar minuten is de feed bereikbaar op:
   `https://<jouw-gebruikersnaam>.github.io/files-feed/feed.xml`
7. **Controleren.** Open die URL in je browser. Je zou items moeten zien zoals `A12 | 3,2 km | +12 min`.

## In Power Apps

Voeg via Gegevens de connector **RSS** toe (standaard). Zet dan in `OnVisible` van het scherm, of in `OnTimerEnd` van een Timer met Duration `300000` en Repeat aan:

```
ClearCollect(
    colFiles,
    RSS.ListFeedItems("https://<jouw-gebruikersnaam>.github.io/files-feed/feed.xml")
)
```

Galerie: `Items = colFiles`, met labels `ThisItem.title` (bijvoorbeeld "A12 | 3,2 km | +12 min") en `ThisItem.summary` (de omschrijving van NDW).

## Als de feed leeg blijft of velden ontbreken

Het script zoekt velden op naam, los van de namespaces: `roadNumber`, `queueLength`, `delayTimeValue`, `generalPublicComment`, `latitude` en `longitude`. Dat zijn gangbare DATEX II v3-namen. Hoe NDW ze precies vult, zie je pas aan de echte data. Kijk daarom na de eerste run in **`docs/debug.txt`**. Daarin staan het aantal records per type en de ruwe XML van een voorbeeldrecord. Heet een veld anders, pas dan de naam aan in `zet_om()` in `maak_feed.py`.

## Goed om te weten

- **Vertraging.** GitHub start geplande runs vaak een paar minuten later dan ingesteld. Daarnaast duurt het ±1 minuut voordat Pages een nieuwe versie publiceert. De feed loopt dus 5–15 minuten achter.
- **Automatisch uitschakelen.** In een publieke repository zet GitHub geplande workflows uit na 60 dagen zonder activiteit. Elke run maakt hier een commit (de feed verandert telkens), dus dat gebeurt niet zolang de Action draait. Staat hij toch uit, zet hem dan aan via het tabblad Actions.
- **Bij een fout** (bijvoorbeeld als NDW tijdelijk niet bereikbaar is) blijft de vorige `feed.xml` staan. Je krijgt dan een e-mail van GitHub over de mislukte run.
- **Bron.** De data komt van NDW / Rijkswaterstaat en is open data.
