#!/usr/bin/env bash
# Kommentar «Stand dieser Bewerbung» (Checkliste) im Bewerbungs-Issue anlegen oder
# nachführen. Gemeinsam für application-issue.yml (create: fehlt er, wird er angelegt;
# ein vorhandener bleibt, wie er ist) und commands.yml (update: ein vorhandener wird
# nach einem /outcome-Befehl an das Protokoll angeglichen).
#
#   scripts/stand-kommentar.sh <issue-nummer> <slug> create|update
#
# Umgebung: GH_TOKEN, GITHUB_REPOSITORY.
set -euo pipefail
number="$1"; slug="$2"; mode="${3:-create}"
existing=$(gh api "repos/$GITHUB_REPOSITORY/issues/$number/comments" --paginate \
  --jq "[.[] | select(.user.login == \"github-actions[bot]\" and (.body | contains(\"<!-- jobhunter:stand slug=$slug -->\")))][0].id // empty" | head -n1)
if [ -n "$existing" ] && [ "$mode" != "update" ]; then
  exit 0
fi
if [ -z "$existing" ] && [ "$mode" = "update" ]; then
  exit 0
fi
python -m jobwatch.stand checkliste "applications/$slug" > stand-liste.md
if [ -n "$existing" ]; then
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$existing" -F body=@stand-liste.md >/dev/null
else
  gh issue comment "$number" --body-file stand-liste.md >/dev/null
fi
