# Bewerbungen

Ein Ordner pro Bewerbung: `applications/<firma>-<stelle>/`.

| Datei | Inhalt | Wer schreibt es |
|---|---|---|
| `job.md` | das vollständige Inserat mit Quelle und Abrufdatum | `python -m jobwatch fetch-ad` |
| `cv.yaml` | Lebenslauf-Variante und Motivationsschreiben (Daten für `cv/*.typ`) | Assistent, du prüfst |
| `fit.md` | Anforderung für Anforderung: Belege, Lücken, Empfehlung | Assistent, du prüfst |
| `prep.md` | Vorbereitung für das Vorstellungsgespräch | Assistent, du prüfst |
| `application.md` | Protokoll: Status, Fristen, «So reichst du ein», Outcome log | Assistent + Befehle |
| `guard.md` | Ergebnis der Beleg-Prüfung | `python -m jobwatch.guard` |
| `build/` | fertige PDFs (nicht im Repository, entstehen im Build) | `make cv VARIANT=...` |

Ordner, die mit `_` beginnen, sind Vorlagen und Beispiele und werden von den
Workflows übersprungen: [`_vorlage/`](_vorlage/) und das frei erfundene
Beispiel [`_beispiel-fabrikam-tech-lead/`](_beispiel-fabrikam-tech-lead/).
