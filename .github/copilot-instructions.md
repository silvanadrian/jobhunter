# Anweisungen für GitHub Copilot

Lies zuerst [GUARDRAILS.md](../GUARDRAILS.md) und [AGENTS.md](../AGENTS.md).
Die Schritt-für-Schritt-Anleitungen liegen als Agent Skills in
[`.github/skills/`](skills/): `tailor-application` für ein Bewerbungspaket,
`prepare-interview` für die Gesprächsvorbereitung, `record-application` und
`record-outcome` für das Protokoll, `triage-jobwatch` für das tägliche Issue.

Läufst du als Copilot CLI im Actions-Runner, steht dein Auftrag im Prompt
(`python -m jobwatch.prepare prompt …`): schreibe nur die dort genannten
Dateien, führe keine Befehle aus, frage nicht nach. Guard und Build laufen
danach automatisch.

Kurz:

- Nur Belege aus `profile/evidence.md` (ohne `[unbestätigt]`); jede Aussage im
  Lebenslauf mit `evidence: [E..]`.
- Vor dem Abschluss: `python -m jobwatch.guard applications/<slug>` und
  `make cv VARIANT=applications/<slug>`.
- Schweizer Hochdeutsch für alles, was die Person liest (immer «ss», nie das Eszett).
- Nie einreichen, nie Formulare ausfüllen, nie Konten anlegen.
