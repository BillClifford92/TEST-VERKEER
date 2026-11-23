"""
Zet de NDW open data 'actueel_beeld' (DATEX II v3) om naar een RSS-feed
met actuele files, zodat Power Apps hem kan lezen via de standaard RSS-connector.

Alleen Python-standaardbibliotheek, dus geen pip install nodig.

Instellingen via omgevingsvariabelen (zie .github/workflows/feed.yml):
  WEGEN   kommagescheiden wegnummers, bv. "A12,A50,A325". Leeg = alle wegen.
  BBOX    "minLon,minLat,maxLon,maxLat", bv. "5.0,51.8,6.1,52.2". Leeg = heel NL.
  TYPES   kommagescheiden recordtypes. Standaard "AbnormalTraffic" (= files).
          Bv. "AbnormalTraffic,Accident,VehicleObstruction" voor ook ongevallen/pech.
  BRON    URL van de NDW-data (standaard actueel_beeld.xml.gz).
  INVOER  pad naar een lokaal .xml of .xml.gz bestand (voor testen; overschrijft BRON).
"""

import gzip
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

BRON = os.environ.get("BRON", "https://opendata.ndw.nu/actueel_beeld.xml.gz")
INVOER = os.environ.get("INVOER", "")
WEGEN = [w.strip().upper() for w in os.environ.get("WEGEN", "").split(",") if w.strip()]
BBOX = os.environ.get("BBOX", "").strip()
TYPES = [t.strip() for t in os.environ.get("TYPES", "AbnormalTraffic").split(",") if t.strip()]
UITVOER_MAP = os.environ.get("UITVOER_MAP", "docs")

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


# ---------- hulpfuncties: namespace-onafhankelijk zoeken ----------
# DATEX II gebruikt veel namespaces (sit:, loc:, com:, ...). Door alleen naar de
# 'lokale' naam te kijken, blijft het script werken als NDW prefixes of versies aanpast.

def lokaal(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def alle(el, naam):
    return [e for e in el.iter() if lokaal(e.tag) == naam]


def eerste_tekst(el, naam):
    for e in el.iter():
        if lokaal(e.tag) == naam and e.text and e.text.strip():
            return e.text.strip()
    return ""


def record_type(el):
    t = el.get(XSI_TYPE, "")
    return t.split(":")[-1]


# ---------- data ophalen ----------

def lees_bron():
    if INVOER:
        with open(INVOER, "rb") as f:
            data = f.read()
    else:
        req = urllib.request.Request(BRON, headers={"User-Agent": "ndw-files-feed (GitHub Actions)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    if data[:2] == b"\x1f\x8b":  # gzip-handtekening
        data = gzip.decompress(data)
    return ET.fromstring(data)


# ---------- één situatierecord omzetten ----------

def coordinaten(el):
    lats = [e.text for e in alle(el, "latitude") if e.text]
    lons = [e.text for e in alle(el, "longitude") if e.text]
    paren = []
    for la, lo in zip(lats, lons):
        try:
            paren.append((float(lo), float(la)))
        except ValueError:
            pass
    return paren


def in_bbox(paren):
    if not BBOX:
        return True
    if not paren:
        return True  # geen coördinaten gevonden: liever tonen dan stil weglaten
    x1, y1, x2, y2 = [float(v) for v in BBOX.split(",")]
    return any(x1 <= lo <= x2 and y1 <= la <= y2 for lo, la in paren)


def wegnummer(el):
    nr = eerste_tekst(el, "roadNumber")
    return nr.upper().replace(" ", "")


def weg_past(el):
    nr = wegnummer(el)
    if nr:
        return nr in WEGEN
    # Geen roadNumber in het record? Zoek het wegnummer dan in de omschrijving.
    tekst = " " + omschrijving(el).upper().replace(" ", " ") + " "
    return any(f" {w} " in tekst or f" {w}:" in tekst or f" {w}," in tekst for w in WEGEN)


def omschrijving(el):
    # generalPublicComment > comment > values > value (meestal lang="nl")
    teksten = []
    for gpc in alle(el, "generalPublicComment"):
        for v in alle(gpc, "value"):
            if v.text and v.text.strip():
                if v.get("lang", "nl").lower().startswith("nl"):
                    teksten.insert(0, v.text.strip())
                else:
                    teksten.append(v.text.strip())
    return teksten[0] if teksten else ""


def getal(el, *namen):
    for naam in namen:
        t = eerste_tekst(el, naam)
        if t:
            try:
                return float(t)
            except ValueError:
                pass
    return None


def zet_om(rec):
    rtype = record_type(rec)
    weg = wegnummer(rec)
    lengte_m = getal(rec, "queueLength", "lengthAffected")
    vertraging_s = getal(rec, "delayTimeValue")
    tekst = omschrijving(rec)
    soort = eerste_tekst(rec, "abnormalTrafficType")
    start = eerste_tekst(rec, "overallStartTime") or eerste_tekst(rec, "situationRecordCreationTime")

    delen = [weg or "Onbekende weg"]
    if lengte_m:
        delen.append(f"{lengte_m / 1000:.1f} km".replace(".", ","))
    if vertraging_s:
        delen.append(f"+{round(vertraging_s / 60)} min")
    if rtype != "AbnormalTraffic":
        delen.append(rtype)
    titel = " | ".join(delen)

    return {
        "id": rec.get("id", ""),
        "titel": titel,
        "weg": weg,
        "tekst": tekst or soort or rtype,
        "lengte_m": lengte_m,
        "vertraging_s": vertraging_s,
        "start": start,
        "type": rtype,
    }


# ---------- RSS schrijven ----------

def rss_datum(iso):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return format_datetime(d)
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def schrijf_rss(items, pad):
    nu = format_datetime(datetime.now(timezone.utc))
    regels = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        "<title>Actuele files (NDW open data)</title>",
        "<link>https://opendata.ndw.nu/</link>",
        "<description>Automatisch gegenereerd uit NDW actueel_beeld</description>",
        f"<lastBuildDate>{nu}</lastBuildDate>",
        "<ttl>10</ttl>",
    ]
    if not items:
        items = [{"id": "geen-files", "titel": "Geen files in dit gebied",
                  "tekst": "Er zijn op dit moment geen meldingen.", "weg": "",
                  "start": "", "type": ""}]
    for it in items:
        regels += [
            "<item>",
            f"<title>{escape(it['titel'])}</title>",
            f"<description>{escape(it['tekst'])}</description>",
            "<link>https://www.rijkswaterstaat.nl/wegen/verkeersinformatie</link>",
            f'<guid isPermaLink="false">{escape(it["id"] or it["titel"])}</guid>',
            f"<pubDate>{rss_datum(it['start'])}</pubDate>",
        ]
        if it.get("weg"):
            regels.append(f"<category>{escape(it['weg'])}</category>")
        regels.append("</item>")
    regels += ["</channel>", "</rss>"]
    with open(pad, "w", encoding="utf-8") as f:
        f.write("\n".join(regels) + "\n")


# ---------- hoofdprogramma ----------

def main():
    root = lees_bron()
    records = [e for e in root.iter() if lokaal(e.tag) == "situationRecord"]

    telling = {}
    for r in records:
        telling[record_type(r)] = telling.get(record_type(r), 0) + 1

    items, voorbeeld = [], None
    for r in records:
        if record_type(r) not in TYPES:
            continue
        if voorbeeld is None:
            voorbeeld = r
        if WEGEN and not weg_past(r):
            continue
        if not in_bbox(coordinaten(r)):
            continue
        items.append(zet_om(r))

    # langste vertraging bovenaan
    items.sort(key=lambda i: -(i.get("vertraging_s") or 0))

    os.makedirs(UITVOER_MAP, exist_ok=True)
    schrijf_rss(items, os.path.join(UITVOER_MAP, "feed.xml"))

    # debug.txt: helpt als NDW de structuur wijzigt of velden anders heten
    with open(os.path.join(UITVOER_MAP, "debug.txt"), "w", encoding="utf-8") as f:
        f.write(f"Bron: {INVOER or BRON}\nRecords per type: {telling}\n")
        f.write(f"Filter: TYPES={TYPES} WEGEN={WEGEN or 'alle'} BBOX={BBOX or 'heel NL'}\n")
        f.write(f"Items in feed: {len(items)}\n\n")
        if voorbeeld is not None:
            ET.indent(voorbeeld)
            f.write("Voorbeeld van het eerste record van dit type (ruwe XML):\n")
            f.write(ET.tostring(voorbeeld, encoding="unicode")[:6000])

    print(f"{len(records)} records gelezen, {len(items)} in feed. Types: {telling}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Bij een fout laten we de vorige feed.xml staan, zodat de app blijft werken.
        print(f"FOUT: {exc}", file=sys.stderr)
        sys.exit(1)
