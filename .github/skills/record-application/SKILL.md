---
name: record-application
description: Eine Bewerbung in applications/<slug>/application.md festhalten (Front Matter, Unterlagen, Prüfliste «So reichst du ein», Outcome log), damit nach dem Merge ein Issue mit den PDFs entsteht. Verwenden, wenn ein Paket fertig ist oder eine Bewerbung ohne Paket erfasst werden soll.
---

# Bewerbung erfassen

Zuerst [GUARDRAILS.md](../../../GUARDRAILS.md) lesen, besonders Abschnitt 9
(Einreichen tun Menschen).

## Datei `applications/<slug>/application.md`

Vorlage: `applications/_vorlage/application.md`. Pflicht:

```yaml
---
status: draft            # draft → submitted → interview → offer/accepted | declined | withdrawn
company: "Firma"
role: "Stellentitel"
url: "https://..."
deadline: 2026-12-01     # aus job.md valid_through, sonst leer
submitted_at:            # setzt das Häkchen «Eingereicht» bzw. /outcome submitted
attach:
  - applications/<slug>/build/cv-<slug>.pdf
  - applications/<slug>/build/coverletter-<slug>.pdf
---
```

Danach: `# Bewerbung: <Stelle> bei <Firma>`, der Marker
`<!-- application:<slug> -->` (daran erkennen die Workflows das Issue),
«Was eingereicht wird», «So reichst du ein» (Checkliste mit Link, Dateien,
Fakten aus dem Profil: frühester Stellenantritt, Lohnvorstellung, Pensum,
Arbeitsbewilligung nur wo relevant), `## Application form questions` (Antworten
zum Einfügen, nur aus Belegen) und `## Outcome log`.

## Danach

Commit auf einem Branch, PR, Review durch die Person, Merge. Der Workflow
«Bewerbung als Issue» baut die PDFs und legt das Issue an. Gleiche Firma schon
im Protokoll? `python -m jobwatch.records same-company "<Firma>"` und die
Warnung oben in die Datei schreiben.
