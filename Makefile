# Häufige Befehle. Typst und Python 3 müssen installiert sein (siehe README,
# Abschnitt «Für Fortgeschrittene», oder den Codespace in .devcontainer/).

TYPST ?= typst
PYTHON ?= python3
VARIANT ?=
export TYPST

.PHONY: help cv letter all guard test check clean

help:
	@echo "make cv                              Basis-Lebenslauf -> build/cv.pdf"
	@echo "make cv VARIANT=applications/<slug>  Lebenslauf + Brief einer Bewerbung"
	@echo "make all                             Basis und alle Bewerbungen bauen"
	@echo "make guard [VARIANT=...]             Belege prüfen (GUARDRAILS.md)"
	@echo "make test                            Tests ausführen"
	@echo "make check                           jobhunter.yml prüfen, Feeds anpingen"

cv letter:
	scripts/build-cv.sh $(VARIANT)

all:
	scripts/build-cv.sh
	@for d in applications/[!_]*/; do \
	  if [ -f "$$d/cv.yaml" ]; then scripts/build-cv.sh "$$d" || exit 1; fi; \
	done

guard:
	$(PYTHON) -m jobwatch.guard $(VARIANT)

test:
	$(PYTHON) -m unittest discover -s tests -v

check:
	$(PYTHON) -m jobwatch check

clean:
	rm -rf build applications/*/build
