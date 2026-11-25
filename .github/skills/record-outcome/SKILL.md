---
name: record-outcome
description: Den Stand einer Bewerbung festhalten (eingereicht, Gespräch, Absage, Angebot, keine Antwort, zurückgezogen), das Bewerbungs-Issue schliessen und im Wochen-Check-in nachfragen. Verwenden bei «ich habe eine Absage», «Gespräch vereinbart», «habe eingereicht».
---

# Ergebnis festhalten

Zuerst [GUARDRAILS.md](../../../GUARDRAILS.md) lesen.

## Regeln

- «eingereicht» nur, wenn die Person eine **ausdrückliche Bestätigung** gesehen
  hat (Bestätigungsseite oder Bestätigungsmail). Sonst nachfragen.
- Eine Absage mit bekanntem Grund mit `gap: <Lücke>` notieren. Häufen sich
  gleiche Lücken, schlägt der Wochen-Check-in Vorbereitung vor — nie eine
  Formulierung, die die Lücke versteckt.

## Wege

- Im Bewerbungs-Issue im Kommentar «Stand dieser Bewerbung» das passende
  Kästchen anhaken (Eingereicht, 1. Gespräch, 2. Gespräch, Weitere Runde, Angebot erhalten,
  Absage erhalten, Zurückgezogen). Workflow «Stand einer Bewerbung»
  (`stand.yml`); schon Festgehaltenes wird nicht doppelt eingetragen.
- Mit Notiz oder Grund im Bewerbungs-Issue kommentieren: `/outcome submitted`,
  `/outcome interview Gespräch am 3.12.`, `/outcome declined gap: Führungserfahrung`.
- Im Wochen-Check-in, eine Zeile pro Bewerbung:
  `/status <slug> interview|absage|angebot|keine-antwort|zurückgezogen [Notiz]`.
- Lokal: `python -m jobwatch.outcome applications/<slug> declined --note "gap: ..."`.

Der Workflow «Status-Befehle» schreibt den Eintrag ins `## Outcome log`, setzt
`status:` (und bei «submitted» `submitted_at:`), schliesst das Issue bei einem
abschliessenden Status und verschiebt die Karte auf dem Board (falls
eingerichtet). Steht ein Gespräch an: Skill `prepare-interview` verwenden.
