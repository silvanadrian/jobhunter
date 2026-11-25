"""Template updates: offer a copy the files of a newer jobhunter template.

A repository created with «Use this template» has no link back to the
template. The workflow `update.yml` fetches the template, and this module
decides what to offer:

- Only template paths are compared (code, workflows, docs, examples).
  Personal paths (`jobhunter.yml`, `profile/`, `applications/<slug>/`,
  `.jobwatch/`) are never read, changed or deleted.
- A file is only deleted if it came from the template: it is listed in
  `.jobwatch/vorlage.json` (written by the last accepted update) or, before
  the first update, in the copy's first commit. Files you added yourself stay.
- The built-in GITHUB_TOKEN may not push `.github/workflows/**`. Those files
  are listed in the pull request with instructions, unless a token with the
  Workflows permission is available (`--include-workflows`).
- Every offer carries a fingerprint of its changes in the PR text. An offer
  with the same fingerprint (closed, merged or still open) is not repeated;
  new changes in the template produce a new fingerprint and a new offer.

    python -m jobwatch.vorlage plan --upstream owner/jobhunter --ref FETCH_HEAD \
        --repo me/stellensuche --prs prs.json --out plan.json --body pr.md
    python -m jobwatch.vorlage apply plan.json --ref FETCH_HEAD
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

TEMPLATE_DIRS = (
    ".github/", ".devcontainer/", ".claude/", "jobwatch/", "cv/", "scripts/",
    "fonts/", "docs/", "tests/", "applications/_",
)
TEMPLATE_FILES = {
    "GUARDRAILS.md", "README.md", "AGENTS.md", "CLAUDE.md", "ROADMAP.md",
    "LICENSE", "Makefile", "requirements.txt", "jobhunter.example.yml",
    ".gitignore", "applications/README.md",
}
WORKFLOW_DIR = ".github/workflows/"
STATE_FILE = ".jobwatch/vorlage.json"
BRANCH = "vorlage-update"
TITLE = "Neue Version der Vorlage"
MARKER = "<!-- jobhunter-vorlage: {} -->"
MARKER_RE = re.compile(r"<!-- jobhunter-vorlage: ([0-9a-f+]+) -->")


def is_template_path(path):
    """True for files that belong to the template, never for personal data."""
    return path in TEMPLATE_FILES or path.startswith(TEMPLATE_DIRS)


def is_workflow_path(path):
    return path.startswith(WORKFLOW_DIR)


# --- git ---------------------------------------------------------------------

def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def tree(ref, cwd=None):
    """All files of a commit: {path: (mode, blob sha)}. Submodules are skipped."""
    entries = {}
    for item in git("ls-tree", "-r", "-z", "--full-tree", ref, cwd=cwd).split("\0"):
        if not item:
            continue
        meta, path = item.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "blob":
            entries[path] = (mode, sha)
    return entries


def root_paths(cwd=None):
    """Files of the copy's first commit(s): what «Use this template» brought along."""
    paths = set()
    for root in git("rev-list", "--max-parents=0", "HEAD", cwd=cwd).split():
        paths |= set(tree(root, cwd))
    return paths


def load_state(cwd=None):
    try:
        with open(os.path.join(cwd or ".", STATE_FILE), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# --- what changed ------------------------------------------------------------

def compute_changes(local, upstream, base=None):
    """Template files to add, overwrite or delete so `local` matches `upstream`.

    local, upstream: {path: (mode, sha)} (or any comparable value).
    base: paths known to come from the template. Only those may be deleted;
    None allows every template path.
    """
    added = sorted(p for p in upstream if is_template_path(p) and p not in local)
    changed = sorted(p for p in upstream
                     if is_template_path(p) and p in local and local[p] != upstream[p])
    deleted = sorted(p for p in local
                     if is_template_path(p) and p not in upstream
                     and (base is None or p in base))
    return {"added": added, "changed": changed, "deleted": deleted}


def all_paths(changes):
    return sorted(changes["added"] + changes["changed"] + changes["deleted"])


def fingerprint(changes, upstream, include_workflows=False):
    """Short, stable id of an offer: same changes, same fingerprint."""
    lines = [f"{p} {upstream.get(p, ('-', '-'))[1]}" for p in all_paths(changes)]
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
    if include_workflows and any(is_workflow_path(p) for p in all_paths(changes)):
        digest += "+w"
    return digest


def offered(prs, digest):
    """The PR (dict from `gh pr list --json number,state,body`) that already offered this."""
    for pr in prs:
        if digest in MARKER_RE.findall(pr.get("body") or ""):
            return pr
    return None


def open_pr(prs):
    for pr in prs:
        if str(pr.get("state", "")).upper() == "OPEN":
            return pr
    return None


# --- pull request text -------------------------------------------------------

def _details(summary, lines):
    if not lines:
        return []
    return ["<details>", f"<summary>{summary}</summary>", "", *lines, "", "</details>", ""]


def pr_body(plan):
    up, commit, repo = plan["upstream"], plan["commit"], plan.get("repo") or ""
    base = plan.get("base") or "main"
    changes, pending = plan["changes"], set(plan["pending"])
    applied = {k: [p for p in v if p not in pending] for k, v in changes.items()}
    count = len(all_paths(applied))
    out = [
        "## Neue Version der Vorlage",
        "",
        f"Deine Stellensuche ist eine Kopie der Vorlage [{up}](https://github.com/{up}). "
        "Die Vorlage wird weiterentwickelt: Fehler werden behoben, Abläufe verbessert, "
        "Texte ergänzt. Dieser Entwurf bringt diese Verbesserungen in deine Kopie "
        f"(Stand der Vorlage: [`{commit[:7]}`](https://github.com/{up}/commit/{commit})).",
        "",
        "**Deine persönlichen Daten werden nicht angefasst:** `jobhunter.yml`, alles in "
        "`profile/`, deine Bewerbungen in `applications/` und die gesehenen Stellen "
        "bleiben genau so, wie sie sind. Ersetzt werden nur Dateien der Vorlage "
        "(Programm, Abläufe, Anleitungen, Beispiele). Hast du selbst etwas an einer "
        "dieser Dateien geändert, wird es überschrieben. Welche Dateien es betrifft, "
        "steht in der Liste unten.",
        "",
        "**Übernehmen:** ganz unten auf den grünen Knopf **«Merge pull request»**, dann "
        "**«Confirm merge»**. **Nicht jetzt?** Einfach offen lassen oder schliessen. "
        "Derselbe Entwurf kommt nicht wieder; erst wenn die Vorlage wieder etwas "
        "Neues hat, erscheint ein neuer.",
        "",
    ]
    if count:
        out += _details(f"Geänderte Dateien ({count})",
                        [f"- neu: `{p}`" for p in applied["added"]]
                        + [f"- geändert: `{p}`" for p in applied["changed"]]
                        + [f"- gelöscht: `{p}`" for p in applied["deleted"]])
    if pending:
        out += [
            "### Abläufe von Hand übernehmen (optional)",
            "",
            "GitHub erlaubt einem Ablauf nicht, die Dateien der Abläufe selbst "
            "(`.github/workflows/`) zu ändern. Diese Dateien sind darum **nicht** im "
            "Entwurf. So übernimmst du sie von Hand, jede einzeln:",
            "",
            "1. Den Link «Vorlage» öffnen, oben rechts auf **«Copy raw file»** "
            "(Symbol mit zwei Blättern) klicken.",
            "2. Den Link «bei dir» (bzw. «bei dir anlegen») öffnen, den bisherigen Inhalt "
            "ganz markieren und durch den kopierten ersetzen (bei einer neuen Datei "
            "einfach einfügen), dann **«Commit changes…»** klicken.",
            "3. Bei «gelöscht»: Datei bei dir öffnen, oben rechts **«…» → «Delete "
            "file»**.",
            "",
            "Oder einmalig ein Token einrichten, dann kommen diese Dateien künftig "
            "automatisch mit: [Anleitung «Updates der Vorlage»]"
            f"(https://github.com/{up}/blob/{commit}/docs/FORTGESCHRITTEN.md#updates-der-vorlage).",
            "",
        ]
        lines = []
        for p in sorted(pending):
            source = f"[Vorlage](https://github.com/{up}/blob/{commit}/{p})"
            if p in changes["deleted"]:
                lines.append(f"- gelöscht: `{p}` ([bei dir](https://github.com/{repo}/blob/{base}/{p}))")
            elif p in changes["added"]:
                folder, name = p.rsplit("/", 1)
                lines.append(f"- neu: `{p}`: {source}, "
                             f"[bei dir anlegen](https://github.com/{repo}/new/{base}/{folder}?filename={name})")
            else:
                lines.append(f"- geändert: `{p}`: {source}, "
                             f"[bei dir](https://github.com/{repo}/edit/{base}/{p})")
        out += _details(f"Abläufe ({len(pending)})", lines)
    out += [
        "_Erstellt vom Ablauf «Neue Version der Vorlage» (`update.yml`), läuft monatlich._",
        "",
        MARKER.format(plan["fingerprint"]),
        "",
    ]
    return "\n".join(out)


# --- plan and apply ----------------------------------------------------------

def plan(upstream_name, ref, prs=(), include_workflows=False, repo="", base="main", cwd=None):
    """Compare HEAD with the template at `ref` and decide what to offer.

    status: "same" (nothing to do), "offered" (this exact offer exists already)
    or "new" (create or update the pull request).
    """
    upstream = tree(ref, cwd)
    local = tree("HEAD", cwd)
    state = load_state(cwd)
    known = set(state["files"]) if isinstance(state.get("files"), list) else root_paths(cwd)
    changes = compute_changes(local, upstream, known)
    result = {"status": "same", "upstream": upstream_name, "repo": repo, "base": base,
              "commit": git("rev-parse", ref, cwd=cwd).strip(), "changes": changes}
    paths = all_paths(changes)
    if not paths:
        return result
    digest = fingerprint(changes, upstream, include_workflows)
    pending = [] if include_workflows else [p for p in paths if is_workflow_path(p)]
    template_files = {p for p in upstream if is_template_path(p)}
    # Pending deletions stay in the copy; keep them known so they can still go later.
    template_files |= {p for p in pending if p in changes["deleted"]}
    result.update(fingerprint=digest, pending=pending, files=sorted(template_files))
    previous = offered(prs, digest)
    if previous:
        result.update(status="offered", pr=previous.get("number"))
        return result
    current = open_pr(prs)
    result.update(status="new", open_pr=current.get("number") if current else None)
    return result


def apply(plan_data, ref, cwd=None):
    """Write the offered template files into the working tree and stage them."""
    pending = set(plan_data["pending"])
    changes = plan_data["changes"]
    take = [p for p in changes["added"] + changes["changed"] if p not in pending]
    drop = [p for p in changes["deleted"] if p not in pending]
    if take:
        git("checkout", ref, "--", *take, cwd=cwd)
    if drop:
        git("rm", "-q", "--", *drop, cwd=cwd)
    state = {"upstream": plan_data["upstream"], "commit": plan_data["commit"],
             "fingerprint": plan_data["fingerprint"], "files": plan_data["files"]}
    path = os.path.join(cwd or ".", STATE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    git("add", "-f", "--", STATE_FILE, cwd=cwd)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.vorlage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="Unterschiede zur Vorlage bestimmen")
    p.add_argument("--upstream", required=True, help="owner/repo der Vorlage")
    p.add_argument("--ref", default="FETCH_HEAD")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--base", default="main", help="Hauptbranch der eigenen Kopie")
    p.add_argument("--prs", help="JSON von `gh pr list --json number,state,body`")
    p.add_argument("--include-workflows", action="store_true")
    p.add_argument("--out", required=True)
    p.add_argument("--body", required=True)
    a = sub.add_parser("apply", help="Dateien der Vorlage übernehmen")
    a.add_argument("plan")
    a.add_argument("--ref", default="FETCH_HEAD")
    args = parser.parse_args(argv)

    if args.cmd == "apply":
        with open(args.plan, encoding="utf-8") as handle:
            apply(json.load(handle), args.ref)
        return 0

    prs = []
    if args.prs:
        try:
            with open(args.prs, encoding="utf-8") as handle:
                prs = json.load(handle) or []
        except (OSError, ValueError):
            prs = []
    result = plan(args.upstream, args.ref, prs, args.include_workflows, args.repo, args.base)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False)
    if result["status"] == "same":
        print("::notice::Deine Kopie ist auf dem Stand der Vorlage.", file=sys.stderr)
    elif result["status"] == "offered":
        print(f"::notice::Diese Version wurde schon angeboten (Entwurf #{result.get('pr')}). "
              "Ein neuer Entwurf kommt, sobald die Vorlage wieder etwas Neues hat.", file=sys.stderr)
    else:
        with open(args.body, "w", encoding="utf-8") as handle:
            handle.write(pr_body(result))
        print(f"{len(all_paths(result['changes']))} Datei(en) unterschiedlich, "
              f"{len(result['pending'])} davon Abläufe.", file=sys.stderr)
    print(f"status={result['status']}")
    print(f"open_pr={result.get('open_pr') or ''}")
    print(f"commit={result['commit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
