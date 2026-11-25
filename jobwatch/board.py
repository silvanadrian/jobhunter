"""Optional: Issues auf einem GitHub-Projects-Board (v2) einordnen.

    python -m jobwatch.board move <issue-nummer> Eingereicht

Spalten (Feld «Status» des Boards, Optionen genau so benennen):
    Gefunden → Vorbereitet → Eingereicht → Interview → Absage / Angebot

Wichtig: Das eingebaute GITHUB_TOKEN eines Workflows hat keinen Zugriff auf
Projects-Boards, die einem Benutzerkonto gehören. Dafür braucht es ein
eigenes Token als Secret PROJECT_TOKEN (klassisches Personal Access Token mit
den Scopes `project` und `repo`). Ohne dieses Secret oder mit
`board.enabled: false` macht dieses Skript nichts. Das Board selbst legst du
einmal von Hand an (docs/FORTGESCHRITTEN.md, Abschnitt «Projects-Board»).
"""

import argparse
import json
import os
import sys
import urllib.request

from .config import ConfigError, load

COLUMNS = ["Gefunden", "Vorbereitet", "Eingereicht", "Interview", "Absage", "Angebot"]
STATUS_TO_COLUMN = {"draft": "Vorbereitet", "prepared": "Vorbereitet", "submitted": "Eingereicht",
                    "interview": "Interview", "declined": "Absage", "withdrawn": "Absage", "skipped": "Absage",
                    "offer": "Angebot", "accepted": "Angebot"}


def graphql(query, variables, token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", "GraphQL-Fehler"))
    return data["data"]


PROJECT_Q = """query($owner: String!, $number: Int!) {
  user(login: $owner) { projectV2(number: $number) { id fields(first: 50) { nodes {
    ... on ProjectV2SingleSelectField { id name options { id name } } } } } } }"""
ORG_PROJECT_Q = PROJECT_Q.replace("user(login", "organization(login")
ISSUE_Q = """query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) { issue(number: $number) { id } } }"""
ADD_M = """mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }"""
SET_M = """mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
    value: {singleSelectOptionId: $option}}) { projectV2Item { id } } }"""


def move(issue_number, column, cfg, token, repository):
    board = cfg["board"]
    variables = {"owner": board["owner"], "number": int(board["number"])}
    try:
        project = graphql(PROJECT_Q, variables, token)["user"]["projectV2"]
    except Exception:
        project = graphql(ORG_PROJECT_Q, variables, token)["organization"]["projectV2"]
    field = next((f for f in project["fields"]["nodes"]
                  if f and f.get("name") == board.get("status_field", "Status")), None)
    if not field:
        raise RuntimeError(f"Board hat kein Auswahlfeld «{board.get('status_field', 'Status')}»")
    option = next((o for o in field["options"] if o["name"].lower() == column.lower()), None)
    if not option:
        raise RuntimeError(f"Spalte «{column}» fehlt im Board; vorhanden: "
                           + ", ".join(o["name"] for o in field["options"]))
    owner, repo = repository.split("/")
    issue = graphql(ISSUE_Q, {"owner": owner, "repo": repo, "number": int(issue_number)},
                    token)["repository"]["issue"]["id"]
    item = graphql(ADD_M, {"project": project["id"], "content": issue}, token)[
        "addProjectV2ItemById"]["item"]["id"]
    graphql(SET_M, {"project": project["id"], "item": item, "field": field["id"],
                    "option": option["id"]}, token)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jobwatch.board", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    mv = sub.add_parser("move")
    mv.add_argument("issue")
    mv.add_argument("column", help="Spalte oder Bewerbungsstatus (z. B. submitted)")
    args = parser.parse_args(argv)
    try:
        cfg = load()
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    token = os.environ.get("PROJECT_TOKEN")
    if not cfg["board"]["enabled"] or not token:
        print("Board ausgeschaltet oder kein PROJECT_TOKEN — nichts zu tun.")
        return 0
    column = STATUS_TO_COLUMN.get(args.column, args.column)
    try:
        move(args.issue, column, cfg, token, os.environ.get("GITHUB_REPOSITORY", ""))
    except Exception as exc:
        # Das Board ist optional: ein Fehler hier bricht nie einen Workflow ab.
        print(f"Warnung: Board nicht aktualisiert ({exc})", file=sys.stderr)
        return 0
    print(f"Issue #{args.issue} → {column}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
