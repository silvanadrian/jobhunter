"""Texte rund um den Assistenten (agent: in jobhunter.yml).

    python -m jobwatch.agent token-guide             # Anleitung Fine-grained Token (Notlösung)
    python -m jobwatch.agent local --branch prepare/acme-tech-lead --slug acme-tech-lead
    python -m jobwatch.agent fallback --reason failed --kind paket \\
        --branch prepare/acme-tech-lead --slug acme-tech-lead --log copilot.log

Mit `copilot-cli` schreibt die GitHub Copilot CLI im Actions-Runner die
Dateien. Seit Juli 2026 genügt dafür das eingebaute GITHUB_TOKEN mit der
Workflow-Berechtigung `copilot-requests: write`; die Nutzung zählt auf den
Copilot-Plan des Repository-Besitzers. Nur falls GitHub das ablehnt, braucht
es das Secret COPILOT_GITHUB_TOKEN (Fine-grained Token). Scheitert die CLI oder
ist das Kontingent aufgebraucht, schreibt der Workflow mit `fallback` einen
verständlichen Kommentar und bietet Kopieren & Einfügen an.
"""

import argparse
import re
import sys

from .config import MODELS_RETIRED

SECRET = "COPILOT_GITHUB_TOKEN"
PLANS_URL = "https://github.com/features/copilot/plans"
TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"
FENCE = "`" * 3

# Wie die Optionen im Formular «Einrichtung» heissen und was sie bedeuten.
DESCRIPTIONS = {
    "kopieren": "Kopieren & Einfügen (Standard): Auftrag in claude.ai, ChatGPT o. ä. kopieren, "
                "Antwort mit /paket zurück. Gratis, kein Secret.",
    "copilot-cli": "GitHub Copilot CLI im Actions-Runner. Gratis mit Copilot Free, begrenztes "
                   "Kontingent; normalerweise genügt das eingebaute GITHUB_TOKEN.",
    "copilot": "Copilot-Coding-Agent bearbeitet das Unter-Issue und eröffnet den PR. Ab Copilot Pro.",
    "claude": "Claude Code Action. Secret ANTHROPIC_API_KEY, Abrechnung nach Nutzung bei Anthropic.",
    "none": "lokal: keine KI in GitHub. Das Inserat liegt auf einem Branch, du arbeitest lokal weiter.",
}

# Bekannte Meldungen der Copilot CLI -> Erklärung auf Deutsch.
KNOWN_ERRORS = (
    (r"authentication failed|bad credentials|\b401\b",
     "GitHub hat die Anmeldung der Copilot CLI abgelehnt. Hat dein Konto einen Copilot-Plan "
     "(Copilot Free genügt, <https://github.com/settings/copilot>)? Akzeptiert GitHub das "
     f"eingebaute Token nicht, hilft das Secret `{SECRET}` (Anleitung unten)."),
    (r"access denied by policy settings",
     "Die Copilot CLI ist durch eine Richtlinie gesperrt: in den Copilot-Einstellungen deines "
     "Kontos (<https://github.com/settings/copilot>) oder der Organisation, der das Repository "
     "gehört, die Copilot CLI erlauben."),
    (r"subscription does not include this feature",
     "Dein Copilot-Plan enthält diese Funktion nicht. Alle Pläne inklusive Copilot Free "
     f"enthalten die Copilot CLI; den Plan prüfen: <{PLANS_URL}>."),
    (r"rate.?limit|quota|exceeded|too many requests|\b429\b",
     "Das Kontingent ist aufgebraucht oder ein Rate-Limit greift. Bei Copilot Free ist das "
     "Kontingent begrenzt (200 Chat-Anfragen pro Monat); nächsten Monat erneut versuchen oder "
     "solange Kopieren & Einfügen nutzen; mehr ab "
     f"Copilot Pro: <{PLANS_URL}>."),
    (r"classic personal access tokens|\bghp_",
     "Ein klassisches Token (`ghp_`) wird von Copilot nicht unterstützt. Im Secret "
     f"`{SECRET}` muss ein Fine-grained Token stehen."),
)


def explain(log_text):
    """Erklärungen zu bekannten Fehlermeldungen in der Ausgabe der CLI."""
    return [text for pattern, text in KNOWN_ERRORS if re.search(pattern, log_text or "", re.I)]


def token_guide():
    """Notlösung: Fine-grained Token erstellen und als Secret speichern."""
    return f"""**Nur falls nötig: Secret `{SECRET}` einrichten.** Normalerweise genügt das
eingebaute Token des Workflows. Lehnt GitHub es ab («Authentication failed»), so:

1. Ein neues **Fine-grained** Token erstellen: <{TOKEN_URL}>
   (Profilbild → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token).
2. **Token name:** z. B. `jobhunter Copilot CLI`. **Expiration:** z. B. 90 Tage.
3. **Resource owner:** dein **persönliches Konto**, keine Organisation. Nur dann
   erscheint die Berechtigung «Copilot Requests».
4. **Repository access:** «Public repositories». Tipp: Bei anderer Auswahl fehlt
   «Copilot Requests» manchmal in der Liste.
5. **Permissions** → Reiter **Account** → **Add permissions** → **Copilot Requests**.
   Sonst nichts.
6. **Generate token** und kopieren (beginnt mit `github_pat_`). Klassische Tokens
   (`ghp_`) lehnt Copilot ab.
7. In diesem Repository: **Settings → Secrets and variables → Actions → New
   repository secret**. Name: `{SECRET}`, Wert: das Token, **Add secret**.
"""


def local_steps(kind, branch="", slug=""):
    """Anleitung, um ohne KI in GitHub lokal weiterzuarbeiten."""
    if kind == "ergaenzen":
        return """**Von Hand ergänzen:** In `profile/evidence.md` neue Zeilen nach dem Beispiel
anfügen (neue, noch nie verwendete ID, Markierung `[unbestätigt]` oder nach deiner Prüfung
`[bestätigt]`), bei einer neuen Stelle eine Überschrift `## R<n> | Titel | Firma | Ort | Zeitraum`,
und in `profile/cv.yaml` die passenden Punkte mit `evidence:` ergänzen. Bestehende Einträge
nicht ändern.
"""
    if kind == "profil":
        return """**Lokal weiterarbeiten** (mit der Copilot CLI, Claude Code oder von Hand):

```bash
git pull
# Lebenslauf als Text speichern, z. B. ~/lebenslauf.txt (nicht ins Repository legen)
python -m jobwatch.forms profil-prompt ~/lebenslauf.txt > /tmp/profil-auftrag.md
copilot -p "$(cat /tmp/profil-auftrag.md)" -s --allow-tool='write'   # oder Claude Code
python -m jobwatch.forms profil-check     # setzt alles auf [unbestätigt], prüft die IDs
```

Oder `profile/evidence.md` und `profile/cv.yaml` von Hand nach dem Beispiel ausfüllen.
"""
    package = f"applications/{slug or '<slug>'}"
    return f"""**Lokal weiterarbeiten** (das Inserat liegt schon auf Branch `{branch or 'prepare/<slug>'}`):

```bash
git fetch && git switch {branch or 'prepare/<slug>'}
python -m jobwatch.prepare prompt {package} > /tmp/auftrag.md
copilot -p "$(cat /tmp/auftrag.md)" -s --allow-tool='write'   # oder Claude Code, oder von Hand
python -m jobwatch.prepare finish {package}    # Fakten aus dem Profil, Guard
make cv VARIANT={package}                       # PDFs, Seiten-Check
git add {package} && git commit -m "Bewerbungspaket entworfen" && git push
```

Danach auf GitHub den Pull Request für den Branch eröffnen.
"""


def _tail(path, lines=25):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return ""
    return "\n".join(text.strip().splitlines()[-lines:])


def fallback_message(reason, kind="paket", branch="", slug="", exit_code="", log_text=""):
    """Kommentar für das Issue, wenn die Copilot CLI keinen Entwurf liefern konnte."""
    what = {"profil": "Profil-Entwurf", "ergaenzen": "Ergänzungs-Entwurf"}.get(kind, "Bewerbungspaket")
    command = {"profil": "/profil", "ergaenzen": "/ergaenzen"}.get(kind, "/paket")
    parts = []
    if reason == "retired":
        parts += [f"⚠️ **Kein {what} entworfen.**", "", MODELS_RETIRED]
    elif reason == "no-output":
        parts += [f"⚠️ **Die Copilot CLI lief, hat aber keinen vollständigen {what} geschrieben.**",
                  "", "Meist ist das Kontingent aufgebraucht oder die Antwort wurde abgebrochen."]
    else:
        code = f" (Exit-Code {exit_code})" if str(exit_code) not in ("", "0") else ""
        hints = explain(log_text) or [
            "Das Kontingent von **Copilot Free** ist aufgebraucht (GitHub beziffert es nicht).",
            "Dein Konto hat keinen Copilot-Plan, oder die Copilot CLI ist in den Einstellungen "
            "gesperrt (<https://github.com/settings/copilot>).",
            f"Das eingebaute Token wurde abgelehnt; dann hilft das Secret `{SECRET}`."]
        parts += [f"⚠️ **Die Copilot CLI ist fehlgeschlagen{code}; kein {what} entworfen.**", "",
                  "Mögliche Gründe:", ""] + [f"- {h}" for h in hints]
        if reason == "missing-secret" or any(SECRET in h for h in hints):
            parts += ["", token_guide()]
    parts += ["", "**Sofort weitermachen ohne Copilot:** Im nächsten Kommentar steht ein Auftrag "
                  f"zum Kopieren & Einfügen in deinen Chat; die Antwort mit `{command}` hier einfügen."]
    if log_text:
        parts += ["", "<details><summary>Letzte Zeilen der Ausgabe</summary>", "", FENCE + "text",
                  log_text.replace(FENCE, "'''"), FENCE, "", "</details>"]
    parts += ["", local_steps(kind, branch, slug)]
    return "\n".join(parts).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("token-guide")
    lo = sub.add_parser("local", help="Anleitung für eine lokale Sitzung (agent: lokal)")
    lo.add_argument("--kind", default="paket", choices=("paket", "profil", "ergaenzen"))
    lo.add_argument("--branch", default="")
    lo.add_argument("--slug", default="")
    fb = sub.add_parser("fallback")
    fb.add_argument("--reason", required=True,
                    choices=("missing-secret", "failed", "no-output", "retired"))
    fb.add_argument("--kind", default="paket", choices=("paket", "profil", "ergaenzen"))
    fb.add_argument("--branch", default="")
    fb.add_argument("--slug", default="")
    fb.add_argument("--exit-code", default="")
    fb.add_argument("--log", help="Ausgabe der Copilot CLI; die letzten Zeilen kommen in den Kommentar")
    args = parser.parse_args(argv)
    if args.cmd == "token-guide":
        print(token_guide())
        return 0
    if args.cmd == "local":
        print(local_steps(args.kind, args.branch, args.slug))
        return 0
    print(fallback_message(args.reason, args.kind, args.branch, args.slug, args.exit_code,
                           _tail(args.log) if args.log else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
