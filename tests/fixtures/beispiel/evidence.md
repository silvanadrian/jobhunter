# Belege (evidence.md)

Die einzige Faktenquelle für Lebenslauf, Motivationsschreiben, Passung und
Gesprächsvorbereitung. Jede Aussage zitiert eine ID von hier. Was hier nicht
steht, wird nicht behauptet — siehe [GUARDRAILS.md](../GUARDRAILS.md).

**Beispielperson:** Alex Muster ist frei erfunden. Ersetze alles.

## So ist die Datei aufgebaut

- `## R1 | Titel | Firma | Ort | Zeitraum` beginnt eine Rolle. Die R-IDs
  müssen mit `experience:` in profile/cv.yaml übereinstimmen.
- `- E1: Text` ist ein Beleg. IDs sind eindeutig und ändern sich nie (eine
  gelöschte ID wird nicht neu vergeben).
- Markierungen in eckigen Klammern nach der ID:
  - `[hobby]` — nur privat/in der Freizeit genutzt; der Lebenslauf muss das sagen.
  - `[level: basic]` — Niveau genau so übernehmen, nie aufwerten.
  - `[unbestätigt]` — automatisch aus einem hochgeladenen Lebenslauf entworfen.
    Gesperrt, bis du den Eintrag geprüft und auf `[bestätigt]` geändert hast.
- Schreib dazu, woher der Beleg kommt (Arbeitszeugnis, Projekt, Repository,
  Zertifikat). Konkrete Zahlen nur, wenn du sie belegen kannst.

## R1 | Senior Software Engineer | Contoso AG | Zürich | 03/2022 – heute

- E1 [bestätigt]: Verantwortlich für die technische Weiterentwicklung des Kundenportals (React, TypeScript); Team von fünf Personen. Quelle: Arbeitszeugnis-Entwurf 2024, Stellenbeschreibung.
- E2 [bestätigt]: Playwright-End-to-End-Tests eingeführt und in die CI-Pipeline eingebunden. Quelle: Repository, Pull Requests 2023.
- E3 [bestätigt]: Zwei Junior-Entwicklerinnen durch Code-Reviews und Pair-Programming begleitet (keine disziplinarische Führung). Quelle: Zielvereinbarung 2023.
- E4 [bestätigt]: Build-Prozess von Jenkins auf GitHub Actions migriert. Quelle: Projektdokumentation.

## R2 | Software Engineer | Northwind Analytics GmbH | Bern | 08/2018 – 02/2022

- E5 [bestätigt]: REST-APIs in Python (Django) für interne Auswertungen entwickelt. Quelle: Arbeitszeugnis 2022.
- E6 [bestätigt]: Barrierefreie Formulare nach WCAG 2.1 AA umgesetzt. Quelle: Arbeitszeugnis 2022, Audit-Bericht.
- E7 [bestätigt]: PostgreSQL-Datenmodell inklusive Migrationen betreut. Quelle: Arbeitszeugnis 2022.

## R3 | Junior Web Developer | Fabrikam Web AG | Basel | 09/2016 – 07/2018

- E8 [bestätigt]: Kundenwebsites mit Vue.js und PHP umgesetzt. Quelle: Arbeitszeugnis 2018.

## Allgemein

- E9 [bestätigt] [level: basic]: Node.js — kleinere Hilfsskripte und ein interner Webhook-Dienst bei Contoso. Quelle: Repository.
- E10 [hobby]: Rust — zwei Kommandozeilen-Tools als Hobbyprojekte, nie beruflich eingesetzt. Quelle: privates GitHub-Profil.
- E11 [bestätigt]: Sprachen: Deutsch Muttersprache, Englisch C1 (Zertifikat), Französisch B1.
