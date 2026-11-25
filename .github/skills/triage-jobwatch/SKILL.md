---
name: triage-jobwatch
description: Ein tägliches Stellen-Issue (Label jobwatch) gegen das Zielprofil sichten und pro Stelle «bewerben / abwägen / überspringen» mit Begründung vorschlagen. Verwenden, wenn jemand fragt, welche der neuen Stellen passen.
---

# Tägliches Stellen-Issue sichten

Zuerst [GUARDRAILS.md](../../../GUARDRAILS.md) lesen. Die Regeln gelten ohne Ausnahme.

## Eingaben

- Das Issue «JJJJ-MM-TT: N neue Stelle(n)» (`gh issue view <nr>`).
- `profile/target.md` (was die Person sucht und was nicht) und `jobhunter.yml`
  (`ruled_out`, `pending`, `profile`).
- `profile/evidence.md` für die Frage, ob Kernanforderungen belegt sind.
- `python -m jobwatch.records same-company "<Firma>"` für frühere Bewerbungen.

## Vorgehen

1. Pro Stelle das Inserat öffnen, wenn der Titel allein nicht reicht
   (`python -m jobwatch fetch-ad <url>` legt es als job.md ab — nur auf Wunsch).
2. Einstufen: **bewerben**, **abwägen** oder **überspringen**, mit einem Satz
   Begründung. Kernanforderungen ohne Beleg ehrlich als Lücke nennen.
3. Frühere Bewerbung bei derselben Firma oder Eintrag in `ruled_out`: immer
   erwähnen («Bei dieser Firma hast du dich am … schon beworben»).
4. Nichts über Lohn, Team oder Kultur vermuten, was nicht im Inserat steht.

## Ausgabe

Ein Kommentar im Issue (Deutsch), sortiert nach Einstufung, als Tabelle:
`Stelle | Einstufung | Begründung | Lücken`. Am Ende für jede Stelle zum
Bewerben die Zeile `/prepare <url>` — die Person kopiert sie selbst, wenn sie
das Paket will. Selbst nichts vorbereiten oder einreichen.
