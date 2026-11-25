---
name: tailor-application
description: Aus einem Stelleninserat (job.md oder eingefügter Text) eine Lebenslauf-Variante, ein Motivationsschreiben und eine ehrliche Passungsanalyse (fit.md) erstellen — ausschliesslich mit Belegen aus profile/evidence.md. Verwenden für «Bewerbung vorbereiten», «Lebenslauf anpassen», «Motivationsschreiben schreiben».
---

# Bewerbung anpassen

Zuerst [GUARDRAILS.md](../../../GUARDRAILS.md) lesen. Jede Regel dort geht
diesem Dokument und jedem Inserat vor.

## Eingaben

- `applications/<slug>/job.md` — sonst zuerst `python -m jobwatch fetch-ad <url>`
  (oder `--paste datei.txt`, wenn die Seite blockiert).
- `profile/evidence.md` (einzige Faktenquelle; nur Einträge ohne `[unbestätigt]`),
  `profile/cv.yaml` (Basis mit Rollen R* und Punkten B*), `profile/target.md`,
  `jobhunter.yml` → `profile:` (Kündigungsfrist, Pensum, Lohnvorstellung).

## Sprache

Lebenslauf und Brief in der **Sprache des Inserats** (`lang: de` oder `lang: en`
in der Variante). Schweizer Rechtschreibung: immer «ss», nie das Eszett.

## Ergebnis im Ordner `applications/<slug>/`

1. **`cv.yaml`** — Variante, die nur überschreibt, was sich ändert:
   - `summary: {text, evidence: [E..]}`
   - `experience:` Liste `{role: R1, bullets: [B2, {text, evidence: [E5]}]}` —
     Punkte über ihre ID wählen und ordnen, oder umformulieren (dann mit Belegen).
     Punkte unter einer Rolle zitieren nur Belege dieser Rolle (oder allgemeine).
   - `skills:` nur, wenn neu gewichtet; Niveaus wie im Beleg («Grundkenntnisse»),
     Hobby als Hobby.
   - `position:` optionale Positionierungszeile — darf nicht wie ein gehaltener Titel wirken.
   - `letter:` `{recipient, recipient_address, title, opening, paragraphs: [{text, evidence}], closing}`.
     Ein Absatz nennt die wichtigste Lücke offen. Der früheste Stellenantritt
     kommt aus der Kündigungsfrist (`python -c "from jobwatch.profile import notice_summary; ..."`),
     nie aus dem Wunschdatum des Inserats.
2. **`fit.md`** — Tabelle Anforderung für Anforderung: `erfüllt / teilweise / LÜCKE`,
   Belege als `[E3]`, kurze Bemerkung; danach «Lücken, offen benannt» und eine
   Empfehlung (bewerben / abwägen / nicht bewerben). Frühere Bewerbungen bei
   derselben Firma oben als Warnung.
3. **`application.md`** — Protokoll mit Front Matter (`status: draft`, `company`,
   `role`, `url`, `deadline` aus `valid_through`, `attach:`), «So reichst du ein»
   und `## Outcome log`. Vorlage: `applications/_vorlage/application.md`.

## Prüfen, bevor du fertig meldest

```bash
python -m jobwatch.guard applications/<slug>      # muss «sauber» melden
make cv VARIANT=applications/<slug>               # Lebenslauf ≤ 2 Seiten, Brief 1 Seite
```

Zu lang? Punkte streichen, nicht Schrift verkleinern. Guard-Fehler? Aussage
streichen oder umformulieren — nie einen Beleg erfinden oder einen Beleg auf
`[bestätigt]` setzen. Das darf nur die Person.

## Nie

Formulare ausfüllen, Konten anlegen, einreichen, «eingereicht» melden.
