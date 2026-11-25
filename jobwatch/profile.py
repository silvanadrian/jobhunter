"""Read profile/evidence.md and compute facts that must never be guessed.

evidence.md format (see the template in profile/evidence.md):

    ## R1 | Senior Software Engineer | Example Corp | Zurich, Switzerland | 03/2021 – present
    - E1: Built the billing API in Python/FastAPI; source: performance review 2023
    - E2 [level: basic]: Kubernetes — deployed own services with existing Helm charts
    ## Side projects
    - E9 [hobby]: Rust — command-line tools on GitHub, never used at work
    - E10 [unbestätigt]: drafted from an uploaded CV; unusable until set to [bestätigt]

`## R<n> | title | organisation | location | dates` headings are roles; every
evidence item below one belongs to it. Other headings are free-form groups.
Ids (E1, E2, ...) must be unique and stable: CV bullets cite them.
"""

import calendar
import datetime
import re

ROLE = re.compile(r"^##\s+(R\d+)\s*\|\s*(.*)$")
ITEM = re.compile(r"^\s*[-*]\s+(E\d+)\s*((?:\[[^\]]*\]\s*)*):\s*(.+)$")
HEADING = re.compile(r"^#{1,6}\s")


def parse_evidence(text):
    """Return {"items": {id: {text, tags, role}}, "roles": {Rn: {...}}, "errors": [...]}."""
    items, roles, errors = {}, {}, []
    role = None
    for number, line in enumerate(text.splitlines(), 1):
        hit = ROLE.match(line)
        if hit:
            parts = [p.strip() for p in hit.group(2).split("|")]
            parts += [""] * (4 - len(parts))
            role = hit.group(1)
            roles[role] = {"id": role, "title": parts[0], "org": parts[1],
                           "location": parts[2], "dates": parts[3], "line": number}
            continue
        if HEADING.match(line):
            role = None
            continue
        hit = ITEM.match(line)
        if hit:
            eid, tag_text, body = hit.groups()
            if eid in items:
                errors.append(f"line {number}: duplicate evidence id {eid}")
            tags = [t.strip().lower() for t in re.findall(r"\[([^\]]*)\]", tag_text)]
            items[eid] = {"id": eid, "text": body.strip(), "tags": tags, "role": role,
                          "line": number}
    return {"items": items, "roles": roles, "errors": errors}


UNCONFIRMED = ("unbestätigt", "unbestaetigt", "unconfirmed", "status: unbestätigt",
               "status: unbestaetigt", "status: unconfirmed")


def is_confirmed(item):
    """Entwürfe aus einem hochgeladenen Lebenslauf sind [unbestätigt], bis die
    Person sie prüft und auf [bestätigt] ändert. Ohne Status-Tag gilt ein
    Eintrag als bestätigt (von Hand geschrieben)."""
    return not any(t in UNCONFIRMED for t in item.get("tags", []))


def is_hobby(item):
    return any(t in ("hobby", "personal", "side project") for t in item.get("tags", []))


def add_months(day, months):
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return day.replace(year=year, month=month,
                       day=min(day.day, calendar.monthrange(year, month)[1]))


def earliest_start(today, months, until="month_end"):
    """First possible working day at a new employer after resigning today.

    until=month_end: the notice period must run to the end of a month, so it
    starts on the first of next month (resigning on 14 Nov with 3 months'
    notice ends on 28 Feb; the new job can start on 1 Mar).
    until=any_day: the notice simply runs `months` from today.
    """
    if until == "month_end":
        first_next = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        return add_months(first_next, months)
    return add_months(today, months) + datetime.timedelta(days=1)


def notice_summary(profile, today=None):
    today = today or datetime.date.today()
    notice = profile.get("notice") or {}
    if not notice or notice.get("months") in (None, ""):
        return "Kündigungsfrist nicht in jobhunter.yml (profile.notice) gesetzt — bei der Person nachfragen."
    months = int(notice.get("months"))
    until = notice.get("until", "month_end")
    start = earliest_start(today, months, until)
    rule = "auf Monatsende" if until == "month_end" else "ab Tag der Kündigung"
    return (f"Frühester Stellenantritt bei Kündigung am {today:%d.%m.%Y}: {start:%d.%m.%Y} "
            f"({months} Monate Kündigungsfrist {rule}). Dieses Datum nennen, nicht das "
            "Wunschdatum aus dem Inserat.")
