"""HTTP helper. Every network call in jobwatch goes through fetch(), which
never raises: a feed that is down, blocked or offline simply returns None, so
one broken source can never take the whole run down with it."""

import json
import os
import urllib.request

# Several career sites answer non-browser user agents with an error page, so a
# browser-like default is used. Override with JOBWATCH_USER_AGENT if you prefer
# to identify yourself.
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126 Safari/537.36")


def fetch(url, timeout=15, post=None, headers=None, form=None):
    """GET (or POST JSON / form data) and return the body as text, or None."""
    headers = {"User-Agent": os.environ.get("JOBWATCH_USER_AGENT", DEFAULT_UA),
               **(headers or {})}
    data = None
    if post is not None:
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")
        data = json.dumps(post).encode()
    elif form is not None:
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        data = form.encode()
    request = urllib.request.Request(url, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                return raw.decode(charset, "ignore")
            except LookupError:  # unbekannter Zeichensatz im Header
                return raw.decode("utf-8", "ignore")
    except Exception:
        return None


def fetch_json(url, **kwargs):
    payload = fetch(url, **kwargs)
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None
