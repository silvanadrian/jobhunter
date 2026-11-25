#!/usr/bin/env bash
# Lebenslauf (und Motivationsschreiben) mit Typst bauen und die Seitenzahl prüfen.
#
#   scripts/build-cv.sh                          # Basis aus profile/cv.yaml -> build/cv.pdf
#   scripts/build-cv.sh applications/<slug>      # Variante -> applications/<slug>/build/*.pdf
#
# Umgebungsvariablen: TYPST (Standard: typst), MAX_CV_PAGES (2), MAX_LETTER_PAGES (1).
set -euo pipefail
cd "$(dirname "$0")/.."

TYPST=${TYPST:-typst}
MAX_CV_PAGES=${MAX_CV_PAGES:-2}
MAX_LETTER_PAGES=${MAX_LETTER_PAGES:-1}
FLAGS=(--root . --font-path fonts --ignore-system-fonts)
for photo in profile/foto.jpg profile/foto.jpeg profile/foto.png; do
  if [ -f "$photo" ]; then FLAGS+=(--input "photo=/$photo"); break; fi
done

pages() {  # pages <file.typ> [--input ...]
  "$TYPST" query "${FLAGS[@]}" "$@" "<page-count>" --field value --one
}

dir=${1:-}
dir=${dir%/}
if [ -z "$dir" ]; then
  mkdir -p build
  "$TYPST" compile "${FLAGS[@]}" cv/cv.typ build/cv.pdf
  n=$(pages cv/cv.typ)
  echo "build/cv.pdf: $n Seite(n)"
  [ "$n" -le "$MAX_CV_PAGES" ] || { echo "FEHLER: Lebenslauf hat $n Seiten, erlaubt sind $MAX_CV_PAGES" >&2; exit 1; }
  exit 0
fi

test -f "$dir/cv.yaml" || { echo "FEHLER: $dir/cv.yaml fehlt" >&2; exit 1; }
slug=$(basename "$dir")
input=(--input "variant=/$dir/cv.yaml")
mkdir -p "$dir/build"

"$TYPST" compile "${FLAGS[@]}" "${input[@]}" cv/cv.typ "$dir/build/cv-$slug.pdf"
n=$(pages cv/cv.typ "${input[@]}")
echo "$dir/build/cv-$slug.pdf: $n Seite(n)"
status=0
if [ "$n" -gt "$MAX_CV_PAGES" ]; then
  echo "FEHLER: Lebenslauf hat $n Seiten, erlaubt sind $MAX_CV_PAGES — Punkte streichen statt Schrift verkleinern" >&2
  status=1
fi

if grep -q '^letter:' "$dir/cv.yaml"; then
  "$TYPST" compile "${FLAGS[@]}" "${input[@]}" cv/letter.typ "$dir/build/coverletter-$slug.pdf"
  m=$(pages cv/letter.typ "${input[@]}")
  echo "$dir/build/coverletter-$slug.pdf: $m Seite(n)"
  if [ "$m" -gt "$MAX_LETTER_PAGES" ]; then
    echo "FEHLER: Motivationsschreiben hat $m Seiten, erlaubt ist $MAX_LETTER_PAGES" >&2
    status=1
  fi
fi
exit $status
