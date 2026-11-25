#!/usr/bin/env bash
# Ergänzung des Profils (profile/evidence.md, profile/cv.yaml) committen und den
# Entwurf (Pull Request) eröffnen oder aktualisieren, mit einer Checkliste nur für
# die neuen Belege. Aufgerufen von ergaenzen.yml (Copilot CLI und /ergaenzen).
#
# Umgebung: ISSUE (Nummer des Formular-Issues), NEW_IDS (neue Beleg-IDs, kommagetrennt),
# SOURCE (wer geschrieben hat).
set -euo pipefail
branch="ergaenzen/issue-$ISSUE"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -B "$branch"
git add profile/evidence.md profile/cv.yaml
git diff --staged --quiet || git commit -m "Profil-Ergänzung entworfen (Issue #$ISSUE)"
git push -f -u origin "$branch"
count=$(echo "$NEW_IDS" | tr ',' '\n' | grep -c .)
cat > pr.md <<MD
Ergänzung deines Profils aus dem Formular «Profil ergänzen» (Issue #$ISSUE), geschrieben von
$SOURCE. **Neu sind $count Einträge** ($NEW_IDS); alle bisherigen Belege, Stellen und Punkte
sind unverändert (vom Programm geprüft).

## Was du jetzt machst

1. **Neue Belege bestätigen:** Unten in den Kommentaren steht eine **Checkliste** mit den neuen
   Einträgen. Hake jeden an, der genau so stimmt. Nur Angehaktes kommt in deinen Lebenslauf.
2. **Übernehmen:** Sobald unten «✅ Ehrlichkeits-Prüfung bestanden» steht, ganz unten auf den
   grünen Knopf **«Merge pull request»** klicken, dann **«Confirm merge»**.

<details><summary>Für Fortgeschrittene</summary>

- Die neuen Zeilen stehen in \`profile/evidence.md\` und \`profile/cv.yaml\` (Reiter «Files changed»).
  Du kannst sie hier im Entwurf direkt bearbeiten (Stift-Symbol); danach wird automatisch neu geprüft.
- Eine neue Stelle steht oben unter \`experience:\`, neue Kurse oben unter \`education:\`.
  Eine Kenntnis, deren Gruppe es schon gibt, steht als eigene Zeile mit «(ergänzt)»; zusammenführen
  kannst du sie nach dem Übernehmen von Hand.
- Markierungen: \`[hobby]\` für nur privat Genutztes, \`[level: basic]\` für Grundkenntnisse.

</details>
MD
title="Profil ergänzen: $count neue Einträge"
existing=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty')
if [ -n "$existing" ]; then
  gh pr edit "$existing" --title "$title" --body-file pr.md
else
  url=$(gh pr create --title "$title" --body-file pr.md --head "$branch" --base main) \
    || { echo "::error::PR nicht erstellt. Ist «Allow GitHub Actions to create and approve pull requests» eingeschaltet?"; exit 1; }
  existing="${url##*/}"
fi
# Checkliste nur mit den neuen Belegen (ersetzt eine ältere aus einem früheren Entwurf).
python -m jobwatch.belege checkliste "$branch" --only "$NEW_IDS" > liste.md
old=$(gh api "repos/$GITHUB_REPOSITORY/issues/$existing/comments" --paginate \
  --jq '[.[] | select(.user.login == "github-actions[bot]" and (.body | contains("<!-- jobhunter:belege branch=")))][0].id // empty' | head -n1)
if [ -n "$old" ]; then
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$old" -F body=@liste.md >/dev/null
else
  gh pr comment "$existing" --body-file liste.md
fi
gh issue comment "$ISSUE" --body "✅ Entwurf erstellt. **Als Nächstes:** im Entwurf #$existing die neuen Einträge abhaken und übernehmen."
gh issue close "$ISSUE" || true
