---
title: "Von 900.000 auf 3: S3-Kosten durch inkrementelles Caching drastisch reduzieren"
date: 2026-05-28T00:00:00+02:00
lastmod: 2026-05-28T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: false
description: "Wie ein stündlicher Lambda-Job unbemerkt hunderttausende S3-Requests erzeugt hat — und wie drei gezielte Änderungen das Problem von Grund auf gelöst haben."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "S3", "Athena", "Lambda", "Analytics", "Cost Optimization", "Serverless", "SAM"]
lightgallery: true
---

{{< listen >}}

$4,64 in zwei Tagen. Für einen Blog mit überschaubarem Traffic ist das eine unerwartete Überraschung im AWS Cost Explorer. Der Schuldige war schnell gefunden — aber die Lösung führte durch drei Iterationen, die sich lohnen aufzuschreiben.

## Das Problem

Mein [Analytics-System](/posts/2026-05-18-privacy-analytics/) besteht aus Kinesis Firehose → S3 → Athena. Ein stündlicher Lambda-Job fragt Athena ab und schreibt das Ergebnis als JSON in S3, wo das Dashboard es liest.

Die ursprüngliche Lambda sah konzeptionell so aus:

```python
# Jeden 4 Queries, jede über 30 Tage
SELECT page, COUNT(*) FROM page_views
WHERE timestamp >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY page
```

Vier Queries. Stündlich. Klingt harmlos.

## Warum Athena so viele S3-Requests erzeugt

Athena ist kein Datenbankserver mit Index — es ist ein Query-Engine die direkt auf S3-Dateien arbeitet. Für jede Query macht Athena intern:

1. **LIST** — alle Dateien in den relevanten Partitionen aufzählen
2. **GET** — jede Datei einzeln lesen und dekomprimieren
3. **PUT** — Ergebnisse in `athena-results/` schreiben

Mit Hive-Partitionen nach `year/month/day` und 30 Tagen History bedeutet das ~30 Partition-Prefixes pro Query, jeder mit mehreren GZIP-Files. Vier Queries, 24 Mal pro Tag:

```text
4 Queries × ~8.000 S3-Requests/Query × 24 Runs/Tag ≈ 768.000 Tier-1-Requests/Tag
```

Tier-1 (PUT/LIST) kostet $0,005 pro 1.000 Requests in eu-central-1 — das sind knapp $4/Tag.

## Schritt 1: Athena nur noch die aktuelle Stunde scannen lassen

Die Kerneinsicht: Das Dashboard braucht 30-Tage-Daten, aber Athena muss nicht bei jedem Run 30 Tage scannen. Wenn man stündliche Snapshots akkumuliert, reicht es, Athena nur die **aktuelle Stunde** zu fragen.

```python
# Nur ein Tag als Partition, nur eine Stunde als Timestamp-Filter
where = (
    f"year = '{year}' AND month = '{month}' AND day = '{day}'"
    f" AND from_iso8601_timestamp(\"timestamp\") >= TIMESTAMP '{ts_start}'"
    f" AND from_iso8601_timestamp(\"timestamp\") <  TIMESTAMP '{ts_end}'"
)
```

Der Partition-Filter begrenzt Athena auf einen Tag (statt 30), der Timestamp-Filter auf eine Stunde. Das Ergebnis wird als `cache/hourly/YYYY-MM-DD-HH.json` gespeichert. Die Lambda merged dann alle vorhandenen Hourly-Files in Python zu einem Dashboard.

**Ersparnis: ~97%** der Athena-Scan-Kosten.

## Schritt 2: Den Merge-Schritt optimieren

Wer genau hinschaut, sieht das nächste Problem: Jede Stunde alle bis zu 720 Hourly-Files lesen (`30 Tage × 24h`) bedeutet 720 S3-GET-Requests pro Run.

Die Lösung: statt alle Files neu zu lesen, ein akkumuliertes `merged_state.json` pflegen — ein Dict mit allen Stunden als Keys:

```json
{
  "2026-05-27-14": {
    "top_articles": [["page", "views"], ...],
    "daily_traffic": [...],
    ...
  }
}
```

Jeder Lambda-Run macht dann nur noch:

1. GET `merged_state.json`
2. Athena für die letzte Stunde abfragen
3. Neue Stunde einfügen, Stunden > 30 Tage entfernen
4. PUT `merged_state.json`
5. PUT `dashboard.json`

**3 S3-Requests pro Run** statt 720.

## Schritt 3: Die richtige Stunde abfragen

Noch ein subtiler Bug: Der ursprüngliche Code fragte die **aktuelle** Stunde ab:

```python
hour_start = now.replace(minute=0, second=0, microsecond=0)  # z.B. 14:00
hour_end   = hour_start + timedelta(hours=1)                  # 15:00
```

Wenn die Lambda um 14:05 feuert, enthält der Snapshot für Stunde 14 nur 5 Minuten Daten. Die restlichen 55 Minuten werden nie nachgeholt.

Fix: immer die **vorherige abgeschlossene Stunde** abfragen:

```python
hour_end   = now.replace(minute=0, second=0, microsecond=0)  # 14:00
hour_start = hour_end - timedelta(hours=1)                    # 13:00
```

Run um 14:05 → vollständige Stunde 13:00–14:00. Keine Datenlücken, 1 Stunde Verzögerung im Dashboard.

## Das Ergebnis

| | Vorher | Nachher |
| --- | --- | --- |
| Athena scannt | 30 Tage / Run | 1 Stunde / Run |
| S3-Requests / Run | ~8.000 | 3 |
| S3-Requests / Tag | ~768.000 | ~72 |
| Geschätzte Kosten / Tag | bis zu ~$3 | <$0,01 |

Dazu kommt ein einmaliger **Backfill-Lambda**, der die letzten 30 Tage als historische Stunden-Snapshots aufbereitet — damit das Dashboard beim ersten Run nicht leer ist.

## Fazit

Das Muster lässt sich verallgemeinern: Wann immer eine periodische Query historische Daten neu berechnet, lohnt es sich zu fragen — muss das wirklich jedes Mal von vorne sein? Oft reicht ein kleines akkumuliertes State-Objekt, um den Scan auf das Neue zu begrenzen. Ähnlich wie ein inkrementelles Backup: nur die Änderungen, nicht alles.

Der vollständige Code ist auf [GitHub](https://github.com/AWS-Sensei/Blog/tree/main/apis/analytics) zu finden.

---

{{< chat >}}
