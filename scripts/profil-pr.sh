#!/usr/bin/env bash
# Profil-Entwurf (profile/evidence.md, profile/cv.yaml) committen und den Pull
# Request eröffnen oder aktualisieren. Gemeinsam für profil.yml (Copilot CLI)
# und paket.yml (/profil, Kopieren & Einfügen).
#
# Umgebung: ISSUE (Nummer des Profil-Issues), CHECK_CODE (0 = sauber),
# SOURCE (wer geschrieben hat). check.txt enthält die Ausgabe von profil-check.
set -euo pipefail
branch="profil/issue-$ISSUE"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -B "$branch"
python -m jobwatch.forms stil || true
git add profile/evidence.md profile/cv.yaml
[ -f jobhunter.yml ] && git add jobhunter.yml
git add -A profile/foto.* 2>/dev/null || true; git add -u profile/ 2>/dev/null || true
git diff --staged --quiet || git commit -m "Profil aus dem Lebenslauf entworfen"
git push -f -u origin "$branch"
{
  if [ "$CHECK_CODE" != "0" ]; then
    echo "> [!CAUTION]"
    echo "> **Prüfung fehlgeschlagen.** Der Entwurf hat formale Fehler; bitte korrigieren:"
    echo ">"; sed 's/^/> /' check.txt; echo
  fi
  cat <<MD
Entwurf deines Profils aus deinem Lebenslauf (Issue #$ISSUE), geschrieben von $SOURCE.

## Was du jetzt machst

1. **Belege bestätigen:** Unten in den Kommentaren steht eine **Checkliste**. Hake jeden
   Punkt an, der genau so stimmt. Nur angehakte Punkte kommen in deinen Lebenslauf.
2. **Übernehmen:** Sobald unten «✅ Ehrlichkeits-Prüfung bestanden» steht, ganz unten auf
   den grünen Knopf **«Merge pull request»** klicken, dann **«Confirm merge»**.

Danach bist du startklar: Bewerbungspakete für einzelne Stellen bereitest du mit
\`/prepare <Link zum Inserat>\` in einem Issue vor.

<details><summary>Für Fortgeschrittene</summary>

- Die Belege stehen in \`profile/evidence.md\`, der Basis-Lebenslauf in \`profile/cv.yaml\`.
  Beide kannst du hier im Entwurf direkt bearbeiten (Reiter «Files changed», Stift-Symbol).
  Nach jeder Änderung wird automatisch neu geprüft.
- Markierungen: \`[hobby]\` für nur privat Genutztes, \`[level: basic]\` für Grundkenntnisse.
- Eine kurze Zusammenfassung (\`summary:\`) entsteht pro Bewerbung; du kannst auch eine feste
  in \`profile/cv.yaml\` schreiben (mit Belegen).
- Kündigungsfrist, Lohnvorstellung, Pensum und Arbeitsbewilligung stehen in \`jobhunter.yml\`
  unter \`profile:\`, nur aus deinen Formularangaben. Ein Foto liegt unter \`profile/foto.*\`.

</details>
MD
} > pr.md
title="Profil-Entwurf aus Lebenslauf"
[ "$CHECK_CODE" != "0" ] && title="Prüfung fehlgeschlagen – $title"
existing=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty')
if [ -n "$existing" ]; then
  gh pr edit "$existing" --title "$title" --body-file pr.md
else
  url=$(gh pr create --title "$title" --body-file pr.md --head "$branch" --base main) \
    || { echo "::error::PR nicht erstellt. Ist «Allow GitHub Actions to create and approve pull requests» eingeschaltet?"; exit 1; }
  existing="${url##*/}"
fi
# Checkliste zum Bestätigen (ersetzt eine ältere aus einem früheren Entwurf).
python -m jobwatch.belege checkliste "$branch" > liste.md
old=$(gh api "repos/$GITHUB_REPOSITORY/issues/$existing/comments" --paginate \
  --jq '[.[] | select(.user.login == "github-actions[bot]" and (.body | contains("<!-- jobhunter:belege branch=")))][0].id // empty')
if [ -n "$old" ]; then
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$old" -F body=@liste.md >/dev/null
else
  gh pr comment "$existing" --body-file liste.md
fi
gh issue comment "$ISSUE" --body "✅ Entwurf erstellt. **Als Nächstes:** im Entwurf #$existing die Checkliste abhaken und übernehmen."
gh issue close "$ISSUE" || true
