#!/usr/bin/env bash
# Bewerbungspaket committen und den Pull Request eröffnen oder aktualisieren.
# Gemeinsam für prepare.yml (Copilot CLI) und paket.yml (Kopieren & Einfügen).
#
# Umgebung: SLUG TITLE COMPANY BRANCH TASK GUARD_CODE (0 oder 4) SOURCE (wer
# geschrieben hat, z. B. «der GitHub Copilot CLI») RUN_URL (Link auf diesen
# Lauf; dort liegt das Artefakt «lebenslauf-pdfs»). build.txt im aktuellen
# Ordner enthält die Ausgabe von scripts/build-cv.sh.
#
# build.yml läuft absichtlich nicht auf Pull Requests (sonst bräuchte es eine
# Freigabe). Darum liegen die PDFs schon im Artefakt dieses Laufs, und ein
# Kommentar nennt die Seitenzahlen.
set -euo pipefail
dir="applications/$SLUG"
for f in "$dir/cv.yaml" "$dir/guard.md" "$dir/application.md" build.txt; do
  if [ ! -f "$f" ]; then
    echo "::error::$f fehlt: kein fertiges Bewerbungspaket, darum kein Pull Request."
    exit 1
  fi
done
failed=false
if [ "$GUARD_CODE" = "4" ] || grep -q BUILD_FAILED build.txt; then failed=true; fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add "$dir"
git diff --staged --quiet || git commit -m "Bewerbungspaket für $TITLE bei $COMPANY entworfen"
git push -f origin "HEAD:$BRANCH"

{
  if [ "$failed" = true ]; then
    echo "> [!CAUTION]"
    echo "> **Prüfung fehlgeschlagen.** Die Ehrlichkeits-Prüfung oder der Seiten-Check hat Probleme gefunden."
    echo "> Bitte zuerst beheben (Details unten), erst dann übernehmen."
    echo
  fi
  echo "Entwurf für **$TITLE bei $COMPANY**, geschrieben von $SOURCE. Schliesst #$TASK."
  echo
  echo "## Was du jetzt machst"
  echo
  echo "1. **PDFs ansehen:** [Lebenslauf und Brief herunterladen]($RUN_URL#artifacts) (ZIP unten auf der Seite, «lebenslauf-pdfs»)."
  echo "2. **Prüfen:** Stimmt jede Aussage, und würdest du sie im Gespräch genau so vertreten?"
  echo "   - [ ] Lebenslauf und Brief ([\`cv.yaml\`]($dir/cv.yaml))"
  echo "   - [ ] Passung und ehrlich benannte Lücken ([\`fit.md\`]($dir/fit.md))"
  echo "   - [ ] Vorbereitung fürs Gespräch ([\`prep.md\`]($dir/prep.md))"
  echo "3. **Ändern** (falls nötig): Reiter **«Files changed»**, bei der Datei auf **«…» → «Edit file»**. Danach wird automatisch neu geprüft."
  echo "4. **Übernehmen:** ganz unten auf den grünen Knopf **«Merge pull request»**, dann **«Confirm merge»**."
  echo "   Danach erscheint ein Issue mit den fertigen PDFs und einer Anleitung zum Einreichen."
  echo
  echo "## Ehrlichkeits-Prüfung"
  echo
  cat "$dir/guard.md"
  echo
  echo "## Seitenzahl"
  echo
  echo '```text'; cat build.txt; echo '```'
  echo
  awk '/^## So reichst du ein/{p=1} /^## Application form questions/{p=0} p' "$dir/application.md"
  echo
  echo "**Einreichen machst immer du selbst**, auf der Seite der Firma."
} > pr.md

title="Bewerbung: $TITLE bei $COMPANY"
[ "$failed" = true ] && title="Prüfung fehlgeschlagen – $title"
existing=$(gh pr list --head "$BRANCH" --state open --json number --jq '.[0].number // empty')
if [ -n "$existing" ]; then
  gh pr edit "$existing" --title "$title" --body-file pr.md
  number="$existing"
  intro="Entwurf aktualisiert (neue Antwort übernommen)."
else
  url=$(gh pr create --title "$title" --body-file pr.md --head "$BRANCH" --base main) \
    || { echo "::error::PR nicht erstellt. Ist «Allow GitHub Actions to create and approve pull requests» eingeschaltet?"; exit 1; }
  number="${url##*/}"
  intro="PDFs dieses Entwurfs:"
fi

# PDFs mit Seitenzahl als Kommentar, ohne dass jemand einen Workflow freigeben muss.
{
  echo "$intro"
  echo
  pdfs=$(grep -E '\.pdf: [0-9]+ Seite' build.txt | sed -E "s#^.*/build/([^:]+): ([0-9]+) Seite\(n\).*#- \`\1\`: \2 Seite(n)#" || true)
  if [ -n "$pdfs" ]; then echo "$pdfs"; else echo "- (keine PDFs gebaut, siehe Seiten-Check in der Beschreibung)"; fi
  echo
  echo "Herunterladen: [Artefakt «lebenslauf-pdfs»]($RUN_URL#artifacts) dieses Laufs."
  echo "Änderst du etwas am Entwurf, wird automatisch neu geprüft und das Ergebnis hier gemeldet."
} > pdfs.md
gh pr comment "$number" --body-file pdfs.md || true
python -m jobwatch.board move "$TASK" Vorbereitet || true
