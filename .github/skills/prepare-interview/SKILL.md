---
name: prepare-interview
description: Ein Vorbereitungsblatt für ein Vorstellungsgespräch (prep.md) erstellen oder aktualisieren — Pitch, wahrscheinliche Fragen mit STAR-Antwortskizzen aus den Belegen, ehrlicher Umgang mit Lücken, Rahmenbedingungen aus dem Profil. Auch eigenständig verwendbar, sobald ein Gespräch ansteht.
---

# Vorstellungsgespräch vorbereiten

Zuerst [GUARDRAILS.md](../../../GUARDRAILS.md) lesen.

## Eingaben

`applications/<slug>/job.md`, `fit.md` (falls vorhanden), `profile/evidence.md`,
`profile/target.md`, `jobhunter.yml` → `profile:`. Bei einem konkreten Termin
zusätzlich, was die Person über das Gespräch weiss (Gesprächspartner, Format).

## Aufbau von `prep.md` (Vorlage: `applications/_vorlage/prep.md`)

1. **Stelle und Firma** — nur aus dem Inserat und öffentlich Belegbarem.
2. **Warum diese Stelle (Pitch)** — 3–5 Sätze, erste Person, wahr.
3. **Wahrscheinliche Fragen** — 5 bis 8, je mit STAR-Skizze (Situation,
   Aufgabe, Handlung, Ergebnis) **nur aus Belegen**, mit `[E..]`-Verweisen.
   Kein Ergebnis und keine Zahl, die nicht im Beleg steht.
4. **Lücken und wie du sie ehrlich ansprichst** — pro Lücke aus fit.md: was
   stimmt, was du stattdessen mitbringst (belegt), wie du sie schliessen willst.
   Nie umdeuten oder kleinreden.
5. **Auffrischen** — technische Themen aus dem Inserat, die nicht frisch sind.
6. **Fragen an die Firma** — zu Team, Erwartungen, Unklarheiten im Inserat.
7. **Rahmenbedingungen** — frühester Stellenantritt aus der Kündigungsfrist
   (`jobwatch.profile.notice_summary`), Lohnvorstellung, Pensum, Tage vor Ort
   **nur aus dem Profil**. Fehlt etwas: als offene Frage an die Person markieren.
   Lohn recherchieren nur mit Link auf offizielle Rechner (z. B. Salarium des
   Bundesamts für Statistik), keine Zahlen erfinden.
8. **Unklarheiten und Warnzeichen** — Widersprüche im Inserat, unklare Rolle.

Danach `python -m jobwatch.guard applications/<slug>` (prüft die `[E..]`-Verweise).
