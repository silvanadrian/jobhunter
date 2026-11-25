"""Applicant-tracking-system feed adapters.

Most product companies never post on the big job boards; they publish only to
their own ATS. Each adapter turns one ATS's public, unauthenticated listing
endpoint into rows of (title, location, url, salary).

Slug conventions (what goes in `slug:` in jobhunter.yml):

    greenhouse       board token          boards.greenhouse.io/<slug>
    lever            company              jobs.lever.co/<slug>
    ashby            job board name       jobs.ashbyhq.com/<slug>
    personio         subdomain            <slug>.jobs.personio.com
    recruitee        subdomain            <slug>.recruitee.com
    smartrecruiters  company id, optionally "Id?country=ch" (case-sensitive)
    workable         account              apply.workable.com/<slug>
    bamboohr         subdomain            <slug>.bamboohr.com
    breezy           subdomain            <slug>.breezy.hr
    teamtailor       subdomain            <slug>.teamtailor.com
    workday          "tenant/pod/site?search"   e.g. "acme/wd5/External?Zurich"
    jibe             "host?country"       iCIMS/Jibe career sites
    prospective      "medium-id?name"     prospective.ch career sites
    phenom           "host?country"       Phenom career sites
    successfactors   "host?name"          SuccessFactors career-site JSON API
    sfcareers        "host?location"      older SuccessFactors HTML career sites
"""

import html
import json
import re
import urllib.parse

from .filters import GENERIC_OFFICE, money
from .net import fetch

ATS_URLS = {
    # content=true is what carries per-job metadata; without it the only
    # location signal is the free-text field.
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=true",
    "personio": "https://{}.jobs.personio.com/search.json",
    "recruitee": "https://{}.recruitee.com/api/offers/",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{}/postings?limit=100",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{}?details=true",
    "bamboohr": "https://{}.bamboohr.com/careers/list",
    "breezy": "https://{}.breezy.hr/json",
    "teamtailor": "https://{}.teamtailor.com/jobs.json",
    "workday": "https://{}.myworkdayjobs.com/wday/cxs/{}/{}/jobs",
    "jibe": "https://{}/api/jobs?location={}&limit=100&page={}",
}


def greenhouse_location(job):
    """Where the job actually is, not only where the free-text field claims.

    Some boards list a role under one city while the posting's own metadata
    names another. Where a "primary location"-style metadata field exists it
    wins, and the free-text claim stays visible as "(listed as ...)".
    """
    listed = (job.get("location") or {}).get("name", "")
    meta = {str(m.get("name", "")).lower(): m.get("value")
            for m in (job.get("metadata") or [])}
    primary = ", ".join(str(v) for k, v in meta.items()
                        if v and isinstance(v, str) and "primary" in k and
                        ("location" in k or "country" in k))
    if primary:
        if listed and listed.lower() not in primary.lower():
            return f"{primary} (listed as {listed})"
        return primary
    if listed:
        return listed
    # Last resort only: `offices` is the company's office list, not the job's.
    return ", ".join(o.get("name", "") for o in (job.get("offices") or [])
                     if o.get("name") and not GENERIC_OFFICE.search(o["name"]))


def parse(ats, payload):
    """Normalise one ATS payload (str or parsed) into [(title, location, url, salary)]."""
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except ValueError:
            return []
    else:
        data = payload
    if data is None:
        return []

    if ats == "greenhouse":
        return [(j["title"], greenhouse_location(j), j.get("absolute_url", ""),
                 money(j.get("title"))) for j in data.get("jobs", [])]
    if ats == "lever":
        if not isinstance(data, list):
            return []
        return [(j["text"], (j.get("categories") or {}).get("location") or "",
                 j.get("hostedUrl", ""),
                 money((j.get("categories") or {}).get("commitment"), j.get("text"),
                       (j.get("salaryRange") or {}) and json.dumps(j.get("salaryRange"))))
                for j in data]
    if ats == "ashby":
        jobs = []
        for j in data.get("jobs", []):
            comp = j.get("compensation") or {}
            summary = comp.get("compensationTierSummary") if isinstance(comp, dict) else None
            jobs.append((j["title"], j.get("location") or "", j.get("jobUrl", ""),
                         money(summary, j.get("title"))))
        return jobs
    if ats == "personio":
        if not isinstance(data, list):
            return []
        return [(j.get("name", ""), j.get("office", ""), j.get("url", ""), "") for j in data]
    if ats == "recruitee":
        return [(j.get("title", ""), j.get("location", ""), j.get("careers_url", ""),
                 money(j.get("salary"))) for j in data.get("offers", [])]
    if ats == "smartrecruiters":
        jobs = []
        for j in data.get("content", []):
            loc = j.get("location", {})
            where = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
            jobs.append((j.get("name", ""), where, j.get("applyUrl") or j.get("ref", ""), ""))
        return jobs
    if ats == "workable":
        return [(j.get("title", ""), (j.get("location") or {}).get("city", "")
                 if isinstance(j.get("location"), dict) else j.get("city", ""),
                 j.get("url", ""), "") for j in data.get("jobs", [])]
    if ats == "bamboohr":
        jobs = []
        for j in data.get("result", []):
            loc = j.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)
            jobs.append((j.get("jobOpeningName", ""), where,
                         j.get("jobOpeningShareUrl", ""), money(j.get("compensation"))))
        return jobs
    if ats == "breezy":
        if not isinstance(data, list):
            return []
        return [(j.get("name", ""), (j.get("location") or {}).get("name", ""),
                 j.get("url", ""), "") for j in data]
    if ats == "teamtailor":
        jobs = []
        for item in data.get("items", []):
            posting = item.get("_jobposting") or {}
            loc = posting.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            address = (loc.get("address") or {}) if isinstance(loc, dict) else {}
            where = ", ".join(str(x) for x in (address.get("addressLocality"),
                                               address.get("addressCountry"))
                              if x and not isinstance(x, dict))
            if not where and isinstance(address.get("addressCountry"), dict):
                where = address["addressCountry"].get("name", "")
            base = posting.get("baseSalary") or {}
            jobs.append((item.get("title", ""), where, item.get("url", ""),
                         money(json.dumps(base) if base else "")))
        return jobs
    if ats == "jibe":
        base = data.get("_base_url", "")
        return [(j.get("title", ""), j.get("full_location") or j.get("city", ""),
                 f'{base}/careers-home/jobs/{j.get("req_id", "")}', "")
                for j in (item.get("data", {}) for item in data.get("jobs", []))]
    if ats == "workday":
        base = data.get("_base_url", "")
        return [(j.get("title", ""), j.get("locationsText", ""),
                 base + (j.get("externalPath") or ""), "") for j in data.get("jobPostings", [])]
    return []


def _load_workday(slug):
    slug, _, search = slug.partition("?")
    tenant, pod, site = slug.split("/")
    url = ATS_URLS["workday"].format(f"{tenant}.{pod}", tenant, site)
    collected, offset, total = [], 0, 0
    while offset < 400:
        payload = fetch(url, post={"appliedFacets": {}, "limit": 20,
                                   "offset": offset, "searchText": search})
        try:
            data = json.loads(payload or "")
        except ValueError:
            break
        data["_base_url"] = f"https://{tenant}.{pod}.myworkdayjobs.com/en-US/{site}"
        batch = parse("workday", data)
        collected += batch
        # Workday reports the total on the first page only; later pages say 0.
        total = total or data.get("total") or 0
        if len(batch) < 20 or offset + 20 >= total:
            break
        offset += 20
    return tenant, collected


def _load_jibe(slug):
    host, _, country = slug.partition("?")
    collected = []
    for page in range(1, 11):
        payload = fetch(ATS_URLS["jibe"].format(host, urllib.parse.quote(country), page))
        try:
            data = json.loads(payload or "")
        except ValueError:
            break
        data["_base_url"] = f"https://{host}"
        batch = parse("jibe", data)
        collected += batch
        if len(batch) < 100:
            break
    return host.split(".")[-2], collected


def _load_prospective(slug):
    medium, _, name = slug.partition("?")
    jobs, offset = [], 0
    while offset < 1000:
        payload = fetch(f"https://ohws.prospective.ch/public/v1/medium/{medium}/jobs"
                        f"?lang=de&offset={offset}&limit=200")
        try:
            data = json.loads(payload or "")
        except ValueError:
            break
        for j in data.get("jobs", []):
            szas = j.get("szas") or {}
            where = ", ".join(x for x in (szas.get("sza_location.city"),
                                          szas.get("sza_location.country")) if x)
            jobs.append((j.get("title", ""), where, (j.get("links") or {}).get("directlink", ""), ""))
        offset += 200
        if offset >= (data.get("total") or 0):
            break
    return name or medium, jobs


def _load_phenom(slug):
    host, _, country = slug.partition("?")
    jobs, start = [], 0
    while start < 500:
        payload = fetch(f"https://{host}/widgets", post={
            "lang": "en_global", "deviceType": "desktop", "country": "global",
            "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "",
            "subsearch": "", "from": start, "jobs": True, "counts": True,
            "all_fields": ["category", "country", "city"], "size": 50, "clearAll": False,
            "jdsource": "facets", "isSliderEnable": False, "pageId": "page20",
            "siteType": "external", "keywords": "", "global": True,
            "selected_fields": {"country": [country]}})
        try:
            data = json.loads(payload or "")["refineSearch"]["data"]
        except (ValueError, KeyError, TypeError):
            break
        batch = data.get("jobs") or []
        for j in batch:
            where = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            jobs.append((j.get("title", ""), where or j.get("location", ""),
                         f"https://{host}/global/en/job/{j.get('jobId', '')}", ""))
        start += 50
        if len(batch) < 50:
            break
    return host.split(".")[-2], jobs


def _load_successfactors(slug):
    host, _, name = slug.partition("?")
    jobs, page = [], 0
    while page < 40:
        payload = fetch(f"https://{host}/services/recruiting/v1/jobs", post={
            "locale": "en_US", "pageNumber": page, "sortBy": "", "keywords": "",
            "location": "", "facetFilters": {}, "brand": "", "skills": [],
            "categoryId": 0, "alertId": "", "rcmCandidateId": ""})
        try:
            data = json.loads(payload or "")
        except ValueError:
            break
        batch = data.get("jobSearchResult") or []
        for item in batch:
            r = item.get("response") or {}
            places = r.get("jobLocationShort") or []
            parts = (places[0] if places else "").split("|")
            where = ", ".join(dict.fromkeys(p for p in parts[:4] if p))
            jobs.append((r.get("unifiedStandardTitle", ""), where,
                         f"https://{host}/job/{r.get('unifiedUrlTitle', '')}/{r.get('id', '')}-en_US/",
                         ""))
        page += 1
        if not batch or page * 10 >= (data.get("totalJobs") or 0):
            break
    return name or host, jobs


SF_TITLE = re.compile(r'class="jobTitle-link[^"]*"\s+href="(/job/[^"]+)"[^>]*>([^<]+)<')
SF_LOCATION = re.compile(r'<span class="jobLocation">\s*([^<]+?)\s*</span>')


def _load_sfcareers(slug):
    """Older SuccessFactors HTML sites: no JSON, so the result pages are read.
    Each row lists its location twice (desktop and mobile layout)."""
    host, _, where_q = slug.partition("?")
    jobs, start = [], 0
    while start < 500:
        page = fetch(f"https://{host}/search/?q=&locationsearch="
                     f"{urllib.parse.quote(where_q)}&startrow={start}")
        if not page:
            break
        titles = SF_TITLE.findall(page)
        places = SF_LOCATION.findall(page)
        stride = 2 if len(places) == 2 * len(titles) else 1
        for i, (path, title) in enumerate(titles):
            where = places[i * stride] if i * stride < len(places) else where_q
            jobs.append((html.unescape(title.strip()), html.unescape(where),
                         f"https://{host}{path}", ""))
        start += 25
        if len(titles) < 25:
            break
    return host.replace("www.", "").replace("careers.", "").split(".")[0], jobs


CUSTOM_LOADERS = {
    "workday": _load_workday,
    "jibe": _load_jibe,
    "prospective": _load_prospective,
    "phenom": _load_phenom,
    "successfactors": _load_successfactors,
    "sfcareers": _load_sfcareers,
}
SUPPORTED = sorted(set(ATS_URLS) | set(CUSTOM_LOADERS))


def load(feed):
    """Fetch one feed. Returns (display name, [(title, location, url, salary)])."""
    ats, slug = feed["ats"], feed["slug"]
    if ats not in SUPPORTED:
        return feed.get("name") or slug, []
    if ats in CUSTOM_LOADERS:
        name, jobs = CUSTOM_LOADERS[ats](slug)
    else:
        query = ""
        if ats == "smartrecruiters":
            slug, _, query = slug.partition("?")
        payload = fetch(ATS_URLS[ats].format(slug) + (f"&{query}" if query else ""))
        name, jobs = slug, (parse(ats, payload) if payload else [])
    return feed.get("name") or name, jobs


def probe(slug):
    """Try every slug-addressable ATS for a slug; report which ones resolve.

    SmartRecruiters answers unknown companies with an empty list rather than a
    404, so it would give false hits; Workday and Jibe need more than a slug
    (use --probe-workday for Workday).
    """
    found = []
    for ats, template in ATS_URLS.items():
        if ats in ("smartrecruiters", "workday", "jibe"):
            continue
        payload = fetch(template.format(slug))
        if payload is None:
            continue
        jobs = parse(ats, payload)
        # A valid feed with zero openings still counts: it is worth watching.
        if jobs or payload.strip() in ("[]", '{"meta":{"totalCount":0},"result":[]}'):
            found.append((ats, len(jobs)))
    return found


def probe_workday(tenant):
    """Try common Workday pod/site combinations for a tenant."""
    hits = []
    for pod in ("wd1", "wd2", "wd3", "wd5", "wd103"):
        for site in ("External", "Careers", "careers", "ExternalCareerSite",
                     "External_Career_Site", "External_Careers", "Global_Careers", "Jobs"):
            url = ATS_URLS["workday"].format(f"{tenant}.{pod}", tenant, site)
            payload = fetch(url, post={"appliedFacets": {}, "limit": 5, "offset": 0,
                                       "searchText": ""})
            try:
                total = json.loads(payload or "").get("total")
            except (ValueError, AttributeError):
                continue
            if total:
                hits.append((f"{tenant}/{pod}/{site}", total))
    return hits
