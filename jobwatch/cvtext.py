"""profile/cv.yaml als Text ergänzen, ohne den Rest der Datei anzufassen.

Kommentare, Reihenfolge und Schreibweise der Person bleiben erhalten. Neue
Punkte, Kenntnisse und Kurse kommen als je **eine Zeile** im Flow-Stil
(`- {id: B9, text: …, evidence: [E12]}`), damit man sie später zeilenweise
wieder herausnehmen oder zurückholen kann (Checkliste «Belege bestätigen»).
"""

import re

import yaml

FLOW_EVIDENCE = re.compile(r"evidence:\s*\[([^\]]*)\]")
NEW_ROLE = "# neu (Ergänzung)"


def flow(obj):
    """Ein Objekt als einzeilige YAML-Flow-Darstellung."""
    return yaml.safe_dump(obj, default_flow_style=True, allow_unicode=True, sort_keys=False,
                          width=10 ** 9).strip()


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _top_key(lines, key):
    pattern = re.compile(rf"^{re.escape(key)}:\s*(#.*)?$")
    return next((i for i, l in enumerate(lines) if pattern.match(l)), None)


def _block_end(lines, start, indent):
    """Index nach dem letzten Inhalt (ohne Leer-/Kommentarzeilen am Schluss) eines Blocks,
    der bei `start` beginnt und alles umfasst, was tiefer als `indent` eingerückt ist."""
    end = start + 1
    last = start + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _indent(line) <= indent:
            break
        if stripped and not stripped.startswith("#"):
            last = end + 1
        end += 1
    return last


def _list_indent(lines, key_index, default):
    for line in lines[key_index + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and _indent(line) > _indent(lines[key_index]) - 1:
            return _indent(line)
        break
    return default


def _section(lines, key, entries, at_start):
    """Einträge (bereits als Textzeilen ohne Einrückung, je mit «- ») in eine Liste
    auf oberster Ebene einfügen; fehlt der Schlüssel, wird er angehängt."""
    if not entries:
        return lines
    k = _top_key(lines, key)
    if k is None:
        tail = [""] if lines and lines[-1].strip() else []
        return lines + tail + [f"{key}:"] + ["  " + e for e in entries]
    pad = " " * _list_indent(lines, k, 2)
    block = [pad + e for e in entries]
    if at_start:
        pos = k + 1
    else:
        pos = _block_end(lines, k, _indent(lines[k]))
    return lines[:pos] + block + lines[pos:]


def _role_bullets(lines, rid, bullets):
    if not bullets:
        return lines
    role_re = re.compile(rf"^(\s*)-\s+id:\s*{re.escape(rid)}\s*(#.*)?$")
    start = next((i for i, l in enumerate(lines) if role_re.match(l)), None)
    if start is None:
        return lines
    item_indent = _indent(lines[start])
    key_indent = item_indent + 2
    end = _block_end(lines, start, item_indent)
    b = next((i for i in range(start + 1, end)
              if re.match(rf"^ {{{key_indent}}}bullets:\s*(#.*)?$", lines[i])), None)
    if b is None:
        new = [" " * key_indent + "bullets:"] + [" " * (key_indent + 2) + "- " + x for x in bullets]
        return lines[:end] + new + lines[end:]
    pad = " " * _list_indent(lines, b, key_indent + 2)
    pos = _block_end(lines, b, key_indent)
    return lines[:pos] + [pad + "- " + x for x in bullets] + lines[pos:]


def insert(text, roles=(), bullets=None, skills=(), courses=()):
    """Neue Einträge einfügen.

    roles   Liste neuer Stellen (dict mit id, title, org, location, dates, bullets) – oben
    bullets {Rn: [bullet-dict, ...]} für bestehende Stellen – ans Ende ihrer Punkte
    skills  Liste neuer Kenntnis-Zeilen – ans Ende von «skills»
    courses Liste neuer Ausbildungs-Einträge – oben in «education»
    """
    lines = text.splitlines()
    for rid, items in (bullets or {}).items():
        lines = _role_bullets(lines, rid, [flow(b) for b in items])
    role_lines = []
    for role in roles:
        head = {k: role.get(k, "") for k in ("id", "title", "org", "location", "dates")}
        first = True
        for key, value in head.items():
            pair = flow({key: value})[1:-1]          # «{title: Lead}» -> «title: Lead»
            role_lines.append(("- " + pair + "   " + NEW_ROLE) if first else ("  " + pair))
            first = False
        role_lines.append("  bullets:")
        role_lines += ["    - " + flow(b) for b in role.get("bullets") or []]
    lines = _section(lines, "experience", role_lines, at_start=True) if role_lines else lines
    lines = _section(lines, "skills", ["- " + flow(s) for s in skills], at_start=False)
    lines = _section(lines, "education", ["- " + flow(c) for c in courses], at_start=True)
    return "\n".join(lines).rstrip("\n") + "\n"


def cited(line):
    hit = FLOW_EVIDENCE.search(line)
    if not hit or "{" not in line:
        return None
    return [x.strip() for x in hit.group(1).split(",") if x.strip()]


def _drop_empty_new_roles(lines):
    """Neue Stellen (Markierung NEW_ROLE) ohne einen einzigen Punkt ganz entfernen:
    eine Stelle ohne bestätigte Tätigkeit gehört nicht in den Lebenslauf."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.rstrip().endswith(NEW_ROLE) and line.lstrip().startswith("- "):
            indent = _indent(line)
            end = _block_end(lines, i, indent)
            body = lines[i + 1:end]
            if not any(l.strip().startswith("- ") for l in body):
                i = end
                continue
        out.append(line)
        i += 1
    return out


def _subsequence(small, big):
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def align(current_text, draft_text, confirmed, scope):
    """Einzeilige Einträge, die nur Belege aus `scope` zitieren, an die Bestätigung
    angleichen: unbestätigte weglassen, bestätigte (wieder) aufnehmen; neue Stellen
    ohne bestätigten Punkt ganz weglassen. Alle anderen Zeilen bleiben unverändert.

    Hat die Person die Datei im Entwurf selbst bearbeitet (der heutige Text ist
    nicht mehr ein Ausschnitt des Entwurfs), wird nur noch weggelassen, nie
    zurückgeholt, damit ihre Änderungen erhalten bleiben."""
    def keep(line):
        ids = cited(line)
        if ids is None or not set(ids) <= scope:
            return True
        return all(i in confirmed for i in ids)

    current = current_text.splitlines()
    draft = draft_text.splitlines() if draft_text else []
    base = draft if draft and _subsequence(current, draft) else current
    lines = _drop_empty_new_roles([l for l in base if keep(l)])
    return "\n".join(lines).rstrip("\n") + "\n"
