"""Job-board searches, used with --wide.

The first-party ATS feeds are the default and win any duplicate. Boards add
reach (employers without a public feed) but also agency-repost noise, and some
of these endpoints are a site's own internal search rather than a published
API: they work unauthenticated today but can change without notice.

Board entries in a region's `boards:` list:

    - board: jobs.ch        where: [Zürich, Zug]      pages: 3
                            (ohne where: die Orte des Suchgebiets)
"""

import concurrent.futures as futures
import json
import re
import sys
import urllib.parse

from .net import fetch


def _pool_fetch(urls, workers=8, **kwargs):
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda u: fetch(u, **kwargs), urls))


C1_CONTROLS = re.compile("[\u0080-\u009f]")


def fix_c1(text):
    """Windows-1252-Zeichen reparieren, die als C1-Steuerzeichen ankommen.

    Die Suche von jobs.ch liefert manche Titel mit U+0096 statt eines
    Halbgeviertstrichs («80\u0096100 %»): Das Byte 0x96 (cp1252 «–») wurde
    irgendwo als Latin-1 gelesen. Solche Steuerzeichen kommen in echtem Text
    nie vor; sie werden über cp1252 zurückübersetzt (GitHub zeigte sie als �)."""
    def repair(hit):
        try:
            return bytes([ord(hit.group(0))]).decode("cp1252")
        except UnicodeDecodeError:  # 0x81, 0x8d, 0x8f, 0x90, 0x9d sind in cp1252 frei
            return ""
    text = C1_CONTROLS.sub(repair, text or "")
    return fix_lost_dash(text)


def fix_lost_dash(text):
    """Verlorene Gedankenstriche, die schon beim Inserenten zu «?» wurden.

    jobs.ch liefert manche Titel so: «HF/FH ? Psychiatrie … 80?100». Nur zwei
    eindeutige Muster werden repariert: ein «?» mit Leerzeichen auf beiden
    Seiten («a ? b» → «a – b») und eines zwischen zwei Zahlen («80?100» →
    «80–100»). Ein echtes Fragezeichen («Lust auf mehr?») bleibt."""
    text = re.sub(r"(?<=\S) \? (?=\S)", " – ", text or "")
    return re.sub(r"(?<=\d)\?(?=\d)", "–", text)


def jobs_ch(board, queries):
    pages = int(board.get("pages", 3))
    urls = [("https://www.jobs.ch/api/v1/public/search?query={q}&location={w}&rows=20&page={p}")
            .format(q=urllib.parse.quote(q), w=urllib.parse.quote(w), p=p)
            for q in queries for w in board.get("where", []) for p in range(1, pages + 1)]
    rows = []
    for payload in _pool_fetch(urls):
        try:
            data = json.loads(payload or "")
        except ValueError:
            continue
        for j in data.get("documents", []):
            pay = ""
            if j.get("salary_from"):
                pay = f'CHF {j["salary_from"]:,}'.replace(",", "'")
                if j.get("salary_to"):
                    pay += f' - {j["salary_to"]:,}'.replace(",", "'")
            rows.append({"company": fix_c1(j.get("company_name") or "?").strip(),
                         "title": fix_c1(j.get("title") or "").strip(),
                         "location": fix_c1(j.get("place") or "").strip(),
                         "url": (j.get("_links", {}).get("detail_en")
                                 or j.get("_links", {}).get("detail_de") or {}).get("href", ""),
                         "salary": pay, "source": "jobs.ch"})
    return rows


BOARDS = {"jobs.ch": jobs_ch}


def search(region, cfg, broad=False):
    """Run every board configured for a region; returns raw rows."""
    queries = list(cfg["queries"]["lead"]) + (list(cfg["queries"]["broad"]) if broad else [])
    rows = []
    for board in region["boards"]:
        kind = board.get("board")
        func = BOARDS.get(kind)
        if func is None:
            print(f"Warnung: unbekannte Jobbörse {kind!r} bei Ort {region['name']}", file=sys.stderr)
            continue
        q = board.get("queries") or queries
        if kind == "jobs.ch" and not board.get("where"):
            board = {**board, "where": region.get("places") or []}
        rows += func(board, q)
    return rows
