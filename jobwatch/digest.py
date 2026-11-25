"""Tagesübersicht aus der JSON-Ausgabe von jobwatch erzeugen.

    python -m jobwatch.digest new.json --md body.md --html body.html

Markdown für das GitHub-Issue (gekürzt unter GitHubs Limit von 65 536 Zeichen
pro Issue-Text), HTML für die optionale E-Mail. Die Orte erscheinen in der
Reihenfolge aus jobhunter.yml; beim Kürzen fallen zuerst die hinteren weg.
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.parse

MD_LIMIT = 60000
PERCENT = re.compile(r"(\d{2,3})\s*%?\s*(?:[-–—]|bis|to)\s*(\d{2,3})\s*%|(\d{2,3})\s*%")


def percent_range(text):
    """(von, bis) aus «80–100%», «80 - 100 %» oder «60%»; sonst None."""
    hit = PERCENT.search(text or "")
    if not hit:
        return None
    if hit.group(3):
        n = int(hit.group(3))
        return (n, n) if 10 <= n <= 100 else None
    low, high = int(hit.group(1)), int(hit.group(2))
    return (low, high) if 10 <= low <= high <= 100 else None


def assess(job, config):
    """Grobe Einschätzung ohne KI: (Punkte, Hinweis).

    +1 je zusätzlich passendem Stichwort im Titel (über das erste hinaus),
    +1 für ein Stufen-Wort (falls welche gesetzt sind), +1 wenn das Pensum im
    Titel zu deinem passt, -2 wenn es klar nicht passt (dann mit Hinweis)."""
    config = config or {}
    title = (job.get("title") or "").lower()
    search = config.get("search") or {}
    words = [str(k).lower() for k in search.get("keywords") or [] if not str(k).startswith("re:")]
    hits = sum(1 for w in words if w and w in title)
    score = max(0, hits - 1)
    if any(str(s).lower() in title for s in search.get("seniority") or []):
        score += 1
    note = ""
    mine = percent_range((config.get("profile") or {}).get("workload", ""))
    theirs = percent_range(job.get("title"))
    if mine and theirs:
        if theirs[1] >= mine[0] and theirs[0] <= mine[1]:
            score += 1
        else:
            score -= 2
            note = f"Pensum {theirs[0]}–{theirs[1]} % passt nicht zu deinem"
    return score, note


def prepare_link(job):
    """Link auf das Formular «Stelle vorbereiten», Inserat schon eingetragen."""
    server, repo = os.environ.get("GITHUB_SERVER_URL"), os.environ.get("GITHUB_REPOSITORY")
    if not (server and repo and job.get("url")):
        return ""
    query = urllib.parse.urlencode({"template": "stelle-vorbereiten.yml",
                                    "title": f"Stelle: {job.get('title', '')} bei {job.get('company', '')}"[:200],
                                    "link": job["url"]})
    return f"{server}/{repo}/issues/new?{query}"


def build(jobs, order=None, config=None):
    order = order or list(dict.fromkeys(j["region"] for j in jobs))
    md, page = [], ['<div style="font-family:-apple-system,Segoe UI,Helvetica,sans-serif;'
                    'font-size:15px;line-height:1.5;color:#1a1a1a;max-width:640px">']
    for region in order:
        here = [j for j in jobs if j["region"] == region]
        if not here:
            continue
        for j in here:
            j["_score"], j["_hint"] = assess(j, config)
        here.sort(key=lambda j: (-j["_score"], j["company"].lower()))
        good = sum(1 for j in here if j["_score"] >= 2)
        label = here[0].get("region_label") or region
        md.append(f"## {label} — {len(here)} neu\n")
        if good:
            md.append(f"⭐ = passt besonders gut zu deinen Stichwörtern und deinem Pensum ({good}).\n")
        page.append(f'<h2 style="font-size:17px;margin:24px 0 8px">{html.escape(label)} — '
                    f'{len(here)} neu</h2><ul style="padding-left:18px">')
        for j in here:
            extra = f" — `{j['salary']}`" if j.get("salary") else ""
            if j.get("note"):
                extra += f" _({j['note']})_"
            if j["_hint"]:
                extra += f" _({j['_hint']})_"
            star = "⭐ " if j["_score"] >= 2 else ""
            link = prepare_link(j)
            action = f" · [Bewerbung vorbereiten →]({link})" if link else ""
            md.append(f"- {star}**{j['company']}** · [{j['title']}]({j['url']}) · {j['location']}"
                      f"{extra}{action}")
            page.append(f'<li style="margin:6px 0"><strong>{html.escape(j["company"])}</strong> · '
                        f'<a href="{html.escape(j["url"])}">{html.escape(j["title"])}</a> · '
                        f'{html.escape(j["location"])}'
                        + (f' — <code>{html.escape(j["salary"])}</code>' if j.get("salary") else "")
                        + "</li>")
        md.append("")
        page.append("</ul>")
    note = ("Für eine Stelle ein Bewerbungspaket vorbereiten: auf «Bewerbung vorbereiten →» "
            "klicken und im Formular <b>Create</b>. Oder in diesem Issue "
            "<code>/prepare &lt;Link&gt;</code> kommentieren.")
    page.append(f'<p style="font-size:13px;color:#666;margin-top:24px">{note}</p></div>')
    note_md = (note.replace("<code>", "`").replace("</code>", "`").replace("<b>", "**")
               .replace("</b>", "**").replace("&lt;", "<").replace("&gt;", ">"))

    def fit_lines(lines, budget):
        kept, used, listed = [], 0, 0
        for line in lines:
            if used + len(line) + 1 > budget:
                break
            kept.append(line)
            used += len(line) + 1
            listed += line.startswith("- ")
        return kept, listed

    def notice(listed, total):
        return (f"\n> **Gekürzt:** {listed} von {total} Stellen. GitHub begrenzt Issue-Texte "
                "auf 65 536 Zeichen; der Rest steht im Log des Workflow-Laufs.\n")

    total = len(jobs)
    kept, listed = fit_lines(md, MD_LIMIT - len(note_md) - 2)
    extra = []
    if listed < total:
        kept, listed = fit_lines(md, MD_LIMIT - len(note_md) - len(notice(listed, total)) - 3)
        extra = [notice(listed, total)]
    return "\n".join(kept + extra + [note_md]), "".join(page), listed


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.digest", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json_file")
    parser.add_argument("--md", default="body.md")
    parser.add_argument("--html", default="body.html")
    parser.add_argument("--config", help="für die Reihenfolge der Orte")
    args = parser.parse_args(argv)
    jobs = json.load(open(args.json_file, encoding="utf-8"))
    order, config = None, None
    try:
        from .config import load
        config = load(args.config)
        order = list(config["regions"])
    except Exception:
        pass
    body, page, listed = build(jobs, order, config)
    open(args.md, "w", encoding="utf-8").write(body)
    open(args.html, "w", encoding="utf-8").write(page)
    print(f"Issue-Text: {len(body)} Zeichen, {listed} von {len(jobs)} Stellen aufgeführt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
