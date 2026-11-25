"""EIN Stelleninserat vollständig als applications/<firma>-<stelle>/job.md speichern.

    python -m jobwatch fetch-ad URL
    python -m jobwatch fetch-ad URL --paste inserat.txt   # eingefügter Text, falls Abruf scheitert
    python -m jobwatch fetch-ad --paste inserat.txt --company "Acme" --title "Tech Lead"

Lädt genau die eine Seite, die du angegeben hast, einmal und auf Abruf. Das ist
kein Scraper: kein Crawling, keine Paginierung, eine Anfrage pro Aktion (ein
ATS-API-Aufruf ersetzt den Seitenabruf, statt ihn zu ergänzen). Halte dich an
die Nutzungsbedingungen der jeweiligen Seite. Manche Seiten (z. B. LinkedIn)
blockieren automatische Anfragen; dann den Inseratstext einfügen.

Reihenfolge, im Front Matter als `extraction:` festgehalten:

    1. ats-api   öffentliche APIs von Greenhouse, Lever, Ashby, Personio
    2. json-ld   schema.org-JobPosting in der Seite (die meisten Jobbörsen und
                 Karriereseiten: jobs.ch, jobup.ch, StepStone, Teamtailor ...)
    3. meta      OpenGraph-/Meta-Tags plus Haupttext der Seite
    4. paste     mit --paste übergebener Text (in CI: der Issue-Text)

Exit-Codes: 0 geschrieben, 3 nichts Brauchbares gefunden (Inserat einfügen), 2 Bedienfehler.
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from .net import fetch, fetch_json

MIN_TEXT = 400   # characters; below this an extraction is treated as failed


# --- HTML to Markdown ---------------------------------------------------------

class _Markdown(HTMLParser):
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "table", "tr"}
    SKIP = {"script", "style", "noscript", "svg", "nav", "form", "button", "iframe", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.lists, self.href = [], 0, [], None

    def _nl(self, n=2):
        text = "".join(self.out)
        stripped = text.rstrip(" ")
        have = len(stripped) - len(stripped.rstrip("\n"))
        if stripped and have < n:
            self.out.append("\n" * (n - have))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._nl()
            self.out.append("#" * min(int(tag[1]) + 1, 6) + " ")
        elif tag in self.BLOCK:
            self._nl()
        elif tag == "br":
            self.out.append("\n")
        elif tag in ("ul", "ol"):
            self._nl(1 if self.lists else 2)
            self.lists.append([tag, 0])
        elif tag == "li":
            self._nl(1)
            depth = max(len(self.lists) - 1, 0)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.out.append("  " * depth + f"{self.lists[-1][1]}. ")
            else:
                self.out.append("  " * depth + "- ")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("_")
        elif tag == "a":
            self.href = dict(attrs).get("href")
            self.out.append("[")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(self.skip - 1, 0)
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") or tag in self.BLOCK:
            self._nl()
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._nl()
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("_")
        elif tag == "a":
            href = self.href or ""
            self.out.append(f"]({href})" if href.startswith("http") else "]")
            self.href = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_markdown(fragment):
    if not fragment:
        return ""
    if "<" not in fragment and "&lt;" in fragment:
        fragment = html.unescape(fragment)   # Greenhouse double-escapes its HTML
    parser = _Markdown()
    parser.feed(fragment)
    parser.close()
    text = "".join(parser.out)
    text = re.sub(r"\[\]\([^)]*\)|\*\*\s*\*\*|__", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+(?![-\d ])", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- ATS APIs -----------------------------------------------------------------

def _ad(**kw):
    base = {"company": "", "title": "", "location": "", "employment_type": "",
            "date_posted": "", "valid_through": "", "salary": "", "body": ""}
    base.update({k: v or "" for k, v in kw.items()})
    return base


def from_greenhouse(url):
    hit = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w.-]+)/jobs/(\d+)", url)
    if not hit:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "for" in query and "token" in query:
            board, job = query["for"][0], query["token"][0]
        else:
            return None
    else:
        board, job = hit.groups()
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job}?content=true")
    if not data or "title" not in data:
        return None
    return _ad(company=data.get("company_name") or board, title=data["title"],
               location=(data.get("location") or {}).get("name"),
               body=html_to_markdown(data.get("content")))


def from_lever(url):
    hit = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if not hit:
        return None
    eu, company, job = hit.groups()
    data = fetch_json(f"https://api.{'eu.' if eu else ''}lever.co/v0/postings/{company}/{job}")
    if not data or "text" not in data:
        return None
    parts = [html_to_markdown(data.get("description") or "") or data.get("descriptionPlain", "")]
    for section in data.get("lists") or []:
        parts.append(f"## {section.get('text', '')}\n\n" + html_to_markdown(
            f"<ul>{section.get('content', '')}</ul>"))
    parts.append(html_to_markdown(data.get("additional") or "") or data.get("additionalPlain", ""))
    cats = data.get("categories") or {}
    salary = data.get("salaryRange") or {}
    return _ad(company=company, title=data["text"], location=cats.get("location"),
               employment_type=cats.get("commitment"),
               salary=(f"{salary.get('currency', '')} {salary.get('min', '')}-{salary.get('max', '')}"
                       f" {salary.get('interval', '')}".strip() if salary else ""),
               body="\n\n".join(p for p in parts if p))


def from_ashby(url):
    hit = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", url)
    if not hit:
        return None
    board, job = urllib.parse.unquote(hit.group(1)), hit.group(2)
    data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
    for j in (data or {}).get("jobs", []):
        if j.get("id") == job or job in (j.get("jobUrl") or ""):
            comp = j.get("compensation") or {}
            return _ad(company=board, title=j.get("title"), location=j.get("location"),
                       employment_type=j.get("employmentType"),
                       salary=comp.get("compensationTierSummary") if isinstance(comp, dict) else "",
                       body=html_to_markdown(j.get("descriptionHtml")) or j.get("descriptionPlain"))
    return None


def from_personio(url):
    hit = re.search(r"([\w-]+)\.jobs\.personio\.(com|de)/job/(\d+)", url)
    if not hit:
        return None
    company, tld, job = hit.groups()
    payload = fetch(f"https://{company}.jobs.personio.{tld}/xml?language=en")
    if not payload:
        return None
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    for pos in root.iter("position"):
        if (pos.findtext("id") or "").strip() != job:
            continue
        parts = []
        for desc in pos.iter("jobDescription"):
            parts.append(f"## {desc.findtext('name', '').strip()}\n\n"
                         + html_to_markdown(desc.findtext("value", "")))
        return _ad(company=pos.findtext("subcompany") or company, title=pos.findtext("name"),
                   location=pos.findtext("office"), employment_type=pos.findtext("schedule"),
                   body="\n\n".join(parts))
    return None


ATS = [from_greenhouse, from_lever, from_ashby, from_personio]


# --- generic pages: JSON-LD, then meta + main text ---------------------------

LD_JSON = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                     re.S | re.I)


def _walk(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk(node[key])


def _text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("@value") or ""
    if isinstance(value, list):
        return ", ".join(filter(None, (_text(v) for v in value)))
    return str(value or "")


def _place(location):
    places = location if isinstance(location, list) else [location]
    out = []
    for p in places:
        if not isinstance(p, dict):
            out.append(_text(p))
            continue
        addr = p.get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        out.append(", ".join(x for x in (_text(addr.get("addressLocality")),
                                          _text(addr.get("addressRegion")),
                                          _text(addr.get("addressCountry"))) if x))
    return "; ".join(dict.fromkeys(x for x in out if x))


def _salary(base):
    if not isinstance(base, dict):
        return _text(base)
    value = base.get("value") or {}
    currency = base.get("currency", "")
    if isinstance(value, dict):
        low, high = value.get("minValue"), value.get("maxValue")
        amount = value.get("value")
        unit = value.get("unitText", "")
        span = f"{low}-{high}" if low and high else str(amount or low or high or "")
        return f"{currency} {span} {unit}".strip() if span else ""
    return f"{currency} {value}".strip()


def from_json_ld(page):
    for block in LD_JSON.findall(page or ""):
        try:
            data = json.loads(html.unescape(block.strip()) if block.strip().startswith("&") else block.strip())
        except ValueError:
            try:   # some sites leave raw newlines in strings
                data = json.loads(re.sub(r"[\r\n\t]+", " ", block.strip()))
            except ValueError:
                continue
        for node in _walk(data):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "JobPosting" not in kinds:
                continue
            location = _place(node.get("jobLocation") or [])
            if not location and node.get("jobLocationType") == "TELECOMMUTE":
                location = "Remote"
            return _ad(company=_text(node.get("hiringOrganization")),
                       title=html.unescape(_text(node.get("title"))),
                       location=location, employment_type=_text(node.get("employmentType")),
                       date_posted=_text(node.get("datePosted")),
                       valid_through=_text(node.get("validThrough")),
                       salary=_salary(node.get("baseSalary")),
                       body=html_to_markdown(html.unescape(_text(node.get("description")))
                                             if "&lt;" in _text(node.get("description"))
                                             else _text(node.get("description"))))
    return None


def _meta(page, name):
    for pattern in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']'):
        hit = re.search(pattern, page, re.I)
        if hit:
            return html.unescape(hit.group(1)).strip()
    return ""


def from_meta(page):
    if not page:
        return None
    title = _meta(page, "og:title") or html.unescape(
        (re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I) or [None, ""])[1]).strip()
    company = _meta(page, "og:site_name")
    main = re.search(r"<(main|article)\b[^>]*>(.*?)</\1>", page, re.S | re.I)
    if main:
        body_html = main.group(2)
    else:
        body = re.search(r"<body\b[^>]*>(.*)</body>", page, re.S | re.I)
        body_html = body.group(1) if body else page
        body_html = re.sub(r"<(header|footer|nav|aside)\b.*?</\1>", "", body_html, flags=re.S | re.I)
    text = html_to_markdown(body_html)
    if len(text) < MIN_TEXT:
        description = _meta(page, "og:description") or _meta(page, "description")
        text = description if len(description) >= MIN_TEXT else text
    if len(text) < MIN_TEXT:
        return None
    return _ad(company=company, title=title, body=text)


# --- assembling job.md ---------------------------------------------------------

def slugify(text, limit=40):
    plain = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.ASCII)
    plain = re.sub(r"[\s_-]+", "-", plain).strip("-")
    return plain[:limit].rstrip("-") or "unknown"


def extract(url, page_fetcher=fetch):
    """Return (ad dict, extraction method) or (None, reason)."""
    host = urllib.parse.urlparse(url).netloc.lower()
    for adapter in ATS:
        try:
            ad = adapter(url)
        except Exception:
            ad = None
        if ad and len(ad["body"]) >= 50:
            return ad, "ats-api"
    if "linkedin.com" in host:
        return None, "LinkedIn blockiert automatische Anfragen"
    page = page_fetcher(url, timeout=20)
    if not page:
        return None, "die Seite liess sich nicht laden (blockiert, offline oder Login nötig)"
    ad = from_json_ld(page)
    if ad and len(ad["body"]) >= 50:
        return ad, "json-ld"
    ad = from_meta(page)
    if ad:
        return ad, "meta"
    return None, "keine Stellenbeschreibung auf der Seite gefunden"


def render(ad, url, source, extraction, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    front = {"company": ad["company"], "title": ad["title"], "url": url,
             "location": ad["location"], "employment_type": ad["employment_type"],
             "date_posted": ad["date_posted"], "valid_through": ad["valid_through"],
             "salary": ad["salary"], "source": source, "extraction": extraction,
             "fetched_at": now.isoformat()}
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items()
                       if v or k in ("company", "title", "url", "source", "extraction")]
    lines += ["---", "", f"# {ad['title'] or 'Stelleninserat'}" + (f" — {ad['company']}" if ad["company"] else ""),
              "", ad["body"].strip(), ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch fetch-ad", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", default="", help="URL des Inserats")
    parser.add_argument("--paste", help="Datei mit dem Inseratstext, falls der Abruf scheitert ('-' = stdin)")
    parser.add_argument("--company", help="Firmenname setzen/überschreiben")
    parser.add_argument("--title", help="Stellentitel setzen/überschreiben")
    parser.add_argument("--out-dir", default="applications")
    parser.add_argument("--slug", help="Ordnername (Standard: <firma>-<titel>)")
    parser.add_argument("--force", action="store_true", help="bestehende job.md überschreiben")
    parser.add_argument("--print-slug", action="store_true", help="nur den Ordnernamen ausgeben")
    args = parser.parse_args(argv)
    if not args.url and not args.paste:
        parser.error("URL, --paste DATEI oder beides angeben")

    ad, method = (extract(args.url) if args.url else (None, "keine URL angegeben"))
    if ad is None and args.paste:
        text = sys.stdin.read() if args.paste == "-" else open(args.paste, encoding="utf-8").read()
        if len(text.strip()) >= 50:
            ad, method = _ad(body=text.strip()), "paste"
    if ad is None:
        print(f"Inserat nicht auslesbar: {method}.\nBitte den vollständigen Inseratstext ins "
              "Issue einfügen (oder erneut mit --paste inserat.txt --company ... --title ...).",
              file=sys.stderr)
        return 3
    if args.company:
        ad["company"] = args.company
    if args.title:
        ad["title"] = args.title
    if not ad["company"] or not ad["title"]:
        print("Warnung: Firma oder Titel unbekannt; mit --company/--title wird der Ordnername "
              "sprechender", file=sys.stderr)

    host = urllib.parse.urlparse(args.url).netloc.replace("www.", "") if args.url else "pasted"
    slug = args.slug or f"{slugify(ad['company'] or 'company', 24)}-{slugify(ad['title'] or 'role')}"
    folder = os.path.join(args.out_dir, slug)
    path = os.path.join(folder, "job.md")
    if os.path.exists(path) and not args.force:
        print(f"{path} existiert; mit --force überschreiben.", file=sys.stderr)
        if args.print_slug:
            print(slug)
        return 0
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render(ad, args.url, host, method))
    print(slug if args.print_slug else f"{path} geschrieben ({method}, {len(ad['body'])} Zeichen).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
