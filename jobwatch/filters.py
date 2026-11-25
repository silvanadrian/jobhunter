"""Pure functions: title and location filters, salary parsing, dedup keys and
the ruled-out / pending lookups. No network, so they are easy to test."""

import re
import unicodedata

# Money in a title or compensation field: "CHF 140'000", "USD 180,000", "$160k".
SALARY = re.compile(
    r"(?:HK\$|HKD|CHF|USD|US\$|SGD|EUR|GBP|€|£|\$)\s?[\d][\d',.\s]*(?:k|K|m|M)?"
    r"(?:\s?[-–to]{1,3}\s?(?:HK\$|HKD|CHF|USD|EUR|GBP|€|£|\$)?\s?[\d][\d',.\s]*(?:k|K)?)?"
)
# Office names that say nothing about where the job is.
GENERIC_OFFICE = re.compile(r"remote|global|anywhere|worldwide|various|multiple", re.I)


def money(*fields):
    """First salary-looking string among the given fields, or ''."""
    for field in fields:
        if not field:
            continue
        hit = SALARY.search(str(field))
        if hit:
            return re.sub(r"\s+", " ", hit.group(0)).strip()
    return ""


def title_ok(title, cfg, wide_seniority=False, url=""):
    """Does a title pass the engineering, noise, seniority and contract filters?"""
    rx = cfg["_re"]
    if not title:
        return False
    if rx["include"] and not rx["include"].search(title):
        return False
    if rx["exclude"] and rx["exclude"].search(title):
        return False
    if not wide_seniority and rx["seniority"] and not rx["seniority"].search(title):
        return False
    if rx["contract"] and (rx["contract"].search(title) or rx["contract"].search(url or "")):
        return False
    return True


def is_senior(title, cfg):
    rx = cfg["_re"]["seniority"]
    return bool(rx.search(title)) if rx else True


def in_region(location, region):
    """Is this posting somewhere the region allows?

    A location names a listed place, or names only the country without a place
    from the exclude list ("Switzerland" counts, "Geneva, Switzerland" does not
    when Geneva is excluded).
    """
    # Greenhouse rows may carry "(listed as ...)": that half is the claim we
    # distrusted, so only the authoritative half is matched.
    location = (location or "").split(" (listed as")[0]
    rx = region["_re"]
    if rx["exclude_locations"] and rx["exclude_locations"].search(location):
        return False
    if rx["locations"] and rx["locations"].search(location):
        return True
    if rx["country"] and rx["country"].search(location):
        return True
    # remote_ok: "Remote" on its own, or remote within this location's country
    # (already handled above), counts. "Remote - Brazil" does not.
    if rx.get("remote") and rx["remote"].search(location):
        rest = rx["remote"].sub("", location)
        if not re.sub(r"[\W_]+|\b(only|first|friendly|hybrid|or|and)\b", "", rest, flags=re.I):
            return True
    return not rx["locations"] and not rx["country"]   # no location rules: keep all


def dedupe_key(match):
    """Same job from two sources: a squashed company name plus a plain title."""
    company = re.sub(r"\b(ag|sa|gmbh|ltd|limited|inc|co|corp|group|holding|llc|plc)\b", " ",
                     (match.get("company") or "").lower())
    company = re.sub(r"[^a-z0-9]+", "", company)
    title = re.sub(r"[^a-z0-9]+", " ", (match.get("title") or "").lower()).strip()
    return company, title


def already_have(key, keys):
    """True if this job is already listed, allowing for company-name variants.

    A feed slug and a board's legal name rarely match exactly ("acmecorp" vs
    "Acme Corp AG"), so a title match plus either company name containing the
    other counts as the same posting.
    """
    company, title = key
    for other_company, other_title in keys:
        if title != other_title:
            continue
        if company and other_company and (company in other_company or other_company in company):
            return True
    return False


def seen_key(match):
    company, title = dedupe_key(match)
    return f"key:{company}|{title}"


def name_lookup(company, table):
    """Look a company up by whole words: 'Acme Holding AG' matches key 'acme'.

    Accents are folded first, or "Genève" splits into "gen" and "ve". Multi-
    word keys ("acme bank") match as a phrase.
    """
    plain = unicodedata.normalize("NFKD", company or "").encode("ascii", "ignore").decode()
    plain = re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()
    words = set(plain.split())
    for name, why in table.items():
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        if (" " in key and f" {key} " in f" {plain} ") or key in words:
            return why or "eingetragen"
    return None


def annotate(match, cfg):
    """Return (hide, note): hidden if ruled out or applied, noted if pending."""
    why = name_lookup(match["company"], cfg["ruled_out"])
    if why:
        return True, f"ausgeschlossen: {why}"
    if match.get("url") in cfg["applied_urls"]:
        return True, f"beworben: {cfg['applied_urls'][match['url']] or 'ja'}"
    why = name_lookup(match["company"], cfg["pending"])
    if why:
        return False, f"läuft: {why}"
    return False, ""


def yearly_top(label, monthly_below=0):
    """Top of a salary label as a yearly figure, or None if none is stated.

    Handles "$180K – $250K", "USD 180,000-200,000", "CHF 120'000", "$85/hr"
    (annualised at 2080 h) and monthly labels: anything marked per month, or
    any value below `monthly_below` when the board mixes units, is times 12.
    """
    if not label:
        return None
    hourly = re.search(r"/\s?h(ou)?r|hourly|per hour", label, re.I)
    monthly = re.search(r"/\s?m(on)?th|per month|monthly|p\.?\s?m\.?\b|/mo\b", label, re.I)
    thousands = re.search(r"\d\s*[kK]\b", label)
    values = []
    for number, suffix in re.findall(r"(\d[\d,']*(?:\.\d+)?)\s*([kKmM]?)", label):
        value = float(number.replace(",", "").replace("'", ""))
        value *= {"k": 1e3, "m": 1e6}.get(suffix.lower(), 1)
        if 30 <= value < 1000:
            # "$160-220k": the bare 160 shares the k. "$85/hr": annualise.
            value *= 1000 if thousands else (2080 if hourly else 0)
        elif hourly and value < 30:
            value = 0
        if value >= 1000:
            values.append(value)
    if not values:
        return None
    top = max(values)
    if monthly or (monthly_below and top < monthly_below):
        top *= 12
    return top


def below_floor(match, region):
    """Reason string if the stated pay tops out under the region's floor."""
    floors = region.get("_floors") or []
    if not floors:
        return None
    top = yearly_top(match.get("salary"), region.get("monthly_below", 0))
    if top is None:
        return None   # unstated pay is kept
    for floor in floors:
        if floor["where"] is None or floor["where"].search(match.get("location", "")):
            if top < floor["yearly"]:
                return f"Lohn unter {int(floor['yearly']):,}/Jahr".replace(",", "'")
            return None
    return None


def requires_language(text, required, optional_words):
    """True if a sentence names a required language without softening it."""
    if not required or not text:
        return False
    for sentence in re.split(r"(?<=[.;!?\n])\s+|\s+[•·-]\s+", text):
        if required.search(sentence) and not (optional_words and optional_words.search(sentence)):
            return True
    return False
