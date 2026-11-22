#!/usr/bin/env python3
"""Facts and delivery of the workitems skill: a source document broken down into an Azure DevOps
backlog, Epic > Feature > User Story > Task, every item in the same fixed format.

`target` finds the Azure DevOps organization and project (arguments, else the origin remote), the
process and its work item types, the fields of each type with their allowed values, the area and
iteration paths, and the recent backlog items. It writes target.json into a work folder inside the
git directory, so nothing lands in the working tree.

`check` validates plan.json (written by the session) against the rules of the skill and the
process: hierarchy, titles, description skeletons, acceptance criteria, story points, priority
derivation, risk, no tags, predecessor / successor links (no cycle, none inside one branch), and
every `file:line` cited against the repository, with the code a Task quotes found at the line it
names. It writes proposal.md, the view the user approves, and records the fingerprint of the plan
it validated.

`create` creates the items of that exact plan, top-down, with their parent link, then adds the
predecessor / successor links, always on a new item: it refuses a plan changed since its last clean
check, records each created id in created.json and each link in links.json, stops at the first
error, and resumes where it stopped. Every value goes to `az` through a file (`@file`), so no HTML
is ever parsed by a shell.

Reuses factory.py of the code-factory skill (same plugin) for git and the origin patterns.
Stdlib only; every command prints JSON on stdout.

Usage:
    python workitems.py target <document> [--org <org>] [--project <project>]
    python workitems.py check <document> [--sample <key>]
    python workitems.py create <document> [--batch <n>] [--dry-run]

Exit codes: 0 ok, 1 error, 3 the plan breaks a rule (check, create).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code-factory" / "scripts"))
from factory import ORIGIN_ADO, ORIGIN_ADO_SSH, ORIGIN_VS, FactoryError, git, run  # noqa: E402

LEVELS = ("epic", "feature", "story", "task")
STORY_TYPES = (("User Story", "agile"), ("Product Backlog Item", "scrum"), ("Issue", "basic"))
LEVEL_TYPES = {
    "agile": {"epic": "Epic", "feature": "Feature", "story": "User Story", "task": "Task"},
    "scrum": {"epic": "Epic", "feature": "Feature", "story": "Product Backlog Item", "task": "Task"},
    "basic": {"epic": "Epic", "feature": None, "story": "Issue", "task": "Task"},
}

TAGS = "System.Tags"
# plan key -> candidate reference names, the first one the type has wins
FIELDS = {
    "priority": ("Microsoft.VSTS.Common.Priority",),
    "value_area": ("Microsoft.VSTS.Common.ValueArea",),
    "acceptance_criteria": ("Microsoft.VSTS.Common.AcceptanceCriteria",),
    "story_points": ("Microsoft.VSTS.Scheduling.StoryPoints", "Microsoft.VSTS.Scheduling.Effort"),
    "risk": ("Microsoft.VSTS.Common.Risk",),
}
LEVEL_KEYS = {
    "epic": ("priority", "value_area"),
    "feature": ("priority", "value_area"),
    "story": ("priority", "value_area", "acceptance_criteria", "story_points", "risk"),
    "task": ("priority",),
}
COMMON_KEYS = ("key", "level", "parent", "title", "description", "sources", "predecessors", "successors")
SET_BY_SCRIPT = {"System.Title", "System.Description", "System.AreaPath", "System.IterationPath"}

SKELETON = {
    "epic": ("Problem", "Scope"),
    "feature": ("Problem", "Scope", "Done when"),
    "story": ("As a", "I want", "so that", "Current situation", "Paths involved", "Background", "Out of scope"),
    "task": ("Location", "Current code", "Consequence in production", "Expected change"),
}
POINTS = (1, 2, 3, 5, 8)
AC_ITEMS = (4, 8)
TITLE_SOFT_MAX, TITLE_MAX = 90, 255
KEY = re.compile(r"^[A-Za-z0-9_-]+$")
FINDING_ID = re.compile(r"\b[A-Z]{1,6}-\d+\b")
NUMBERING = (
    re.compile(r"^\s*(\d+(\.\d+)*[.)]?|[A-Za-z][.)])\s"),
    re.compile(r"^\s*\["),
    re.compile(r"\b(US|PBI|E|F|T)\s?\d+(\.\d+)*\b"),
    re.compile(r"\b(epic|feature|story|task|item|step|phase)\s*#?\d+\b", re.IGNORECASE),
    FINDING_ID,
)
NOT_AN_ID = re.compile(r"\b(UTF|SHA|AES|ISO|IEC|RSA|TLS|SSL|IEEE|CVE|CWE)-\d+(-\d+)?\b")
DOC_POINTER = re.compile(r"(?:\b(?:section|chapter|appendix|finding)s?|§)\s*\d+(?:\.\d+)*", re.IGNORECASE)
CODE = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
STORY_VERBS_ERROR = {"add", "fix", "implement"}
STORY_VERBS_WARN = {"create", "update", "remove", "refactor", "log", "make", "use", "replace", "move", "rename",
                    "introduce", "handle", "migrate", "delete", "write", "change", "set", "enable", "disable"}
AC_BANNED = re.compile(r"\b(should|properly|correctly|as expected|if needed)\b", re.IGNORECASE)
FILE_REF = re.compile(r"(?<![\w/\\.-])((?:[\w.-]+[/\\])*[\w-][\w.-]*\.[A-Za-z][A-Za-z0-9]{0,5}):(\d+)(?:\s*-\s*(\d+))?")
PRE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
QUOTE_SLACK = 3


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PlanInvalid(FactoryError):
    code = 3


# --- helpers -------------------------------------------------------------------

class _Text(HTMLParser):
    BREAKS = {"br", "p", "div", "li", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.ol: list[int] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "pre", "ol", "ul"):
            self.out.append("\n\n")
        elif tag in self.BREAKS:
            self.out.append("\n")
        if tag == "ol":
            self.ol.append(0)
        elif tag == "ul":
            self.ol.append(-1)
        elif tag == "li":
            if self.ol and self.ol[-1] >= 0:
                self.ol[-1] += 1
                self.out.append(f"{self.ol[-1]}. ")
            else:
                self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in ("ol", "ul") and self.ol:
            self.ol.pop()
        if tag == "pre":
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)


def to_text(value: str | None) -> str:
    """Descriptions are HTML; keep the words and the line breaks."""
    if not value:
        return ""
    parser = _Text()
    parser.feed(value)
    text = html.unescape("".join(parser.out)).replace("\xa0", " ")
    lines = [line.rstrip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def load_json(path: Path, what: str):
    if not path.is_file():
        raise FactoryError(f"{path} not found: {what}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FactoryError(f"{path} is not valid JSON: {e}") from None


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def in_git() -> bool:
    return git("rev-parse", "--show-toplevel", check=False).returncode == 0


def work_folder(document: str) -> Path:
    """One folder per source document, inside the git directory when there is one."""
    if not Path(document).is_file():
        raise FactoryError(f"{document}: no such file")
    slug = re.sub(r"[^a-z0-9]+", "-", Path(document).stem.lower()).strip("-") or "document"
    if in_git():
        base = Path(git("rev-parse", "--git-common-dir").stdout.strip()).resolve() / "workitems"
    else:
        base = Path.cwd() / ".workitems"
    folder = base / slug
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def az(*args: str, org: str):
    proc = run("az", *args, "--org", f"https://dev.azure.com/{org}", "-o", "json")
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def item_url(org: str, project: str, wid: int) -> str:
    q = urllib.parse.quote
    return f"https://dev.azure.com/{q(org)}/{q(project)}/_workitems/edit/{wid}"


# --- target --------------------------------------------------------------------

def org_project(org: str | None, project: str | None) -> tuple[str, str, str]:
    if org and project:
        return org, project, "arguments"
    url = git("remote", "get-url", "origin", check=False).stdout.strip() if in_git() else ""
    for rx in (ORIGIN_ADO, ORIGIN_ADO_SSH, ORIGIN_VS):
        if m := rx.search(url):
            o, p, _ = (urllib.parse.unquote(g) for g in m.groups())
            return org or o, project or p, "origin"
    raise FactoryError("no Azure DevOps project known: origin is not an Azure DevOps repository, "
                       "pass --org and --project", origin=url or None)


def type_fields(org: str, project: str, wtype: str) -> dict:
    data = az("devops", "invoke", "--area", "wit", "--resource", "workItemTypesField",
              "--route-parameters", f"project={project}", f"type={wtype}",
              "--query-parameters", "$expand=allowedValues", "--api-version", "7.1", org=org)
    return {f["referenceName"]: f for f in data.get("value", [])}


def node_paths(node: dict, prefix: str = "") -> list[str]:
    path = f"{prefix}\\{node['name']}" if prefix else node["name"]
    out = [path]
    for child in node.get("children") or []:
        out.extend(node_paths(child, path))
    return out


def recent_items(org: str, project: str, types: list[str]) -> dict:
    names = ", ".join(f"'{t}'" for t in types)
    wiql = ("SELECT [System.Id], [System.WorkItemType], [System.Title], [System.State], [System.AreaPath], "
            "[System.IterationPath], [System.Tags] FROM WorkItems WHERE [System.TeamProject] = @project "
            f"AND [System.WorkItemType] IN ({names}) AND [System.ChangedDate] >= @today - 180 "
            "ORDER BY [System.ChangedDate] DESC")
    try:
        rows = az("boards", "query", "--wiql", wiql, "--project", project, org=org) or []
    except FactoryError as e:
        return {"error": str(e), "items": []}
    items = []
    for row in rows[:40]:
        f = row.get("fields", {})
        items.append({"id": row.get("id"), "type": f.get("System.WorkItemType"), "title": f.get("System.Title"),
                      "state": f.get("System.State"), "area": f.get("System.AreaPath"),
                      "iteration": f.get("System.IterationPath"), "tags": f.get(TAGS)})
    return {"count": len(rows), "items": items}


def target(document: str, org: str | None, project: str | None) -> dict:
    folder = work_folder(document)
    org, project, found_from = org_project(org, project)
    process = az("devops", "project", "show", "--project", project, "--query",
                 "capabilities.processTemplate.templateName", org=org)
    available = az("devops", "invoke", "--area", "wit", "--resource", "workItemTypes",
                   "--route-parameters", f"project={project}", "--api-version", "7.1", org=org)
    names = {t["name"] for t in (available or {}).get("value", [])}
    kind = next((k for t, k in STORY_TYPES if t in names), None)
    if not kind:
        raise FactoryError(f"project {project} has none of the story types {[t for t, _ in STORY_TYPES]}",
                           work_item_types=sorted(names))

    levels = {}
    for level in LEVELS:
        wtype = LEVEL_TYPES[kind][level]
        if not wtype or wtype not in names:
            levels[level] = {"type": None}
            continue
        fields = type_fields(org, project, wtype)
        mapped, missing = {}, []
        for key in LEVEL_KEYS[level]:
            ref = next((r for r in FIELDS[key] if r in fields), None)
            if ref:
                allowed = fields[ref].get("allowedValues") or None
                mapped[key] = {"ref": ref, "allowed": allowed}
            else:
                missing.append(key)
        ours = SET_BY_SCRIPT | {m["ref"] for m in mapped.values()}
        required = sorted(r for r, f in fields.items()
                          if f.get("alwaysRequired") and r not in ours and not r.startswith("System."))
        levels[level] = {"type": wtype, "fields": mapped, "missing": missing, "required_unhandled": required}

    areas = az("boards", "area", "project", "list", "--project", project, "--depth", "4", org=org)
    iterations = az("boards", "iteration", "project", "list", "--project", project, "--depth", "4", org=org)
    backlog_types = [lv["type"] for lv in levels.values() if lv["type"] and lv["type"] != "Task"]
    out = {
        "document": Path(document).as_posix(),
        "org": org, "project": project, "found_from": found_from,
        "process": process, "process_kind": kind, "levels": levels,
        "areas": node_paths(areas) if areas else [project],
        "iterations": node_paths(iterations) if iterations else [project],
        "recent": recent_items(org, project, backlog_types),
        "work_folder": folder.as_posix(),
        "plan_file": (folder / "plan.json").as_posix(),
        "read_at": now(),
    }
    write_json(folder / "target.json", out)
    return out


# --- repository references ---------------------------------------------------------

class Repo:
    """`file:line` references of the plan, resolved against the files git tracks."""

    def __init__(self) -> None:
        self.ok = in_git()
        self.root = Path(git("rev-parse", "--show-toplevel").stdout.strip()) if self.ok else None
        self.files = git("ls-files").stdout.splitlines() if self.ok else []
        self._lines: dict[str, list[str]] = {}

    def resolve(self, ref: str) -> list[str]:
        ref = ref.replace("\\", "/").removeprefix("./").lower()
        return [f for f in self.files if f.lower() == ref or f.lower().endswith("/" + ref)]

    def lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            data = (self.root / rel).read_bytes().decode("utf-8", errors="replace")
            self._lines[rel] = data.splitlines()
        return self._lines[rel]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_refs(where: str, text: str, repo: Repo, errors: list, warnings: list) -> list[tuple[str, int, int]]:
    """Every file:line must exist; returns the references resolved to a single file."""
    resolved = []
    for m in FILE_REF.finditer(text):
        ref, start = m.group(1), int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        files = repo.resolve(ref)
        if not files:
            warnings.append(f"{where}: {ref} is not a file of this repository, {ref}:{start} not verified")
            continue
        if len(files) > 1:
            warnings.append(f"{where}: {ref} matches {len(files)} files ({', '.join(files[:3])}), "
                            "give a longer path")
            continue
        count = len(repo.lines(files[0]))
        if start < 1 or end < start or end > count:
            errors.append(f"{where}: {ref}:{m.group(2)}{'-' + m.group(3) if m.group(3) else ''} is outside "
                          f"{files[0]} ({count} lines)")
            continue
        resolved.append((files[0], start, end))
    return resolved


def check_quotes(where: str, description: str, location: tuple[str, int, int] | None, repo: Repo,
                 errors: list, warnings: list) -> None:
    """The code a Task quotes must be at the location it names."""
    blocks = PRE.findall(description)
    if not blocks:
        warnings.append(f"{where}: Current code quotes no <pre> block")
        return
    if not location:
        return
    rel, start, end = location
    window = [norm(line) for line in repo.lines(rel)[max(start - 1 - QUOTE_SLACK, 0):end + QUOTE_SLACK]]
    for block in blocks:
        for line in html.unescape(TAG.sub("", block)).splitlines():
            s = norm(line)
            if not s or s.strip(".… ") == "" or s.startswith(("...", "…")):
                continue
            if not any(s in w for w in window):
                errors.append(f"{where}: quoted line not found at {rel}:{start}-{end}: {s[:80]}")


# --- check ---------------------------------------------------------------------

def fingerprint(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def numbered(title: str) -> bool:
    cleaned = NOT_AN_ID.sub("", title)
    return any(rx.search(cleaned) for rx in NUMBERING)


def check_self_contained(where: str, value: str, document: str, errors: list, warnings: list) -> None:
    """An item says what the document found; it never sends the reader to the document."""
    if document.lower() in to_text(value).lower():
        errors.append(f"{where}: cites the source document {document}, write what it says instead")
    prose = NOT_AN_ID.sub("", to_text(CODE.sub(" ", value)))
    if pointers := [m.group(0) for m in DOC_POINTER.finditer(prose)]:
        errors.append(f"{where}: '{', '.join(pointers)}' sends the reader to the document, "
                      "write the information itself and keep the reference in sources")
    if ids := sorted(set(FINDING_ID.findall(prose))):
        warnings.append(f"{where}: {', '.join(ids)} mean nothing without the document, "
                        "say what was found and keep the identifier in sources")


def validate(plan: dict, tgt: dict, repo: Repo) -> tuple[list, list, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    levels = tgt["levels"]
    document = Path(tgt["document"]).name
    parent_level = {"feature": "epic", "story": "feature" if levels["feature"]["type"] else "epic", "task": "story"}
    items = plan.get("items")
    if not isinstance(items, list) or not items:
        raise PlanInvalid("plan.json has no items", errors=["plan.json has no items"])
    for key in plan:
        if key not in ("source", "area", "iteration", "items"):
            errors.append(f"plan: unknown key '{key}'")
    for key, paths in (("area", tgt["areas"]), ("iteration", tgt["iterations"])):
        if plan.get(key) and plan[key] not in paths:
            errors.append(f"plan: {key} '{plan[key]}' is not a path of {tgt['project']}")

    by_key: dict[str, dict] = {}
    titles: dict[str, str] = {}
    children: dict[str, list[dict]] = {}
    for i, it in enumerate(items):
        key = it.get("key")
        where = key if isinstance(key, str) and key else f"items[{i}]"
        if not isinstance(key, str) or not KEY.match(key):
            errors.append(f"{where}: key must be letters, digits, '-' or '_'")
        elif key in by_key:
            errors.append(f"{where}: duplicate key")
        level = it.get("level")
        if level not in LEVELS:
            errors.append(f"{where}: level must be one of {', '.join(LEVELS)}")
            continue
        info = levels[level]
        if not info["type"]:
            errors.append(f"{where}: the {tgt['process']} process has no work item type for level {level}")
            continue
        wtype = info["type"]
        by_key[key] = it

        for k in it:
            if k in ("tags", TAGS):
                errors.append(f"{where}: tags are never set")
            elif k not in COMMON_KEYS and k not in LEVEL_KEYS[level]:
                errors.append(f"{where}: '{k}' is not allowed on a {level}")

        parent = it.get("parent")
        if level == "epic" and parent is not None and not isinstance(parent, int):
            errors.append(f"{where}: an epic's parent is null or an existing work item id")
        elif level != "epic":
            if isinstance(parent, bool) or parent is None:
                errors.append(f"{where}: parent is required (a key of the plan or an existing work item id)")
            elif isinstance(parent, str):
                p = by_key.get(parent)
                if not p:
                    errors.append(f"{where}: parent '{parent}' must be a key listed before this item")
                elif p.get("level") != parent_level[level]:
                    errors.append(f"{where}: the parent of a {level} is a {parent_level[level]}, "
                                  f"'{parent}' is a {p.get('level')}")
                else:
                    children.setdefault(parent, []).append(it)
            elif not isinstance(parent, int):
                errors.append(f"{where}: parent must be a key or a work item id")

        title = it.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{where}: title is required")
        else:
            t = title.strip()
            if t != title:
                errors.append(f"{where}: title has leading or trailing spaces")
            if len(t) > TITLE_MAX:
                errors.append(f"{where}: title is {len(t)} characters, Azure DevOps takes {TITLE_MAX}")
            elif len(t) > TITLE_SOFT_MAX:
                warnings.append(f"{where}: title is {len(t)} characters, aim for {TITLE_SOFT_MAX}")
            if t.endswith("."):
                errors.append(f"{where}: title ends with a period")
            if numbered(t):
                errors.append(f"{where}: title carries a number or an identifier: {t}")
            if t.lower() in titles:
                errors.append(f"{where}: same title as {titles[t.lower()]}")
            titles.setdefault(t.lower(), where)
            first = t.split()[0].lower()
            if level == "story" and first in STORY_VERBS_ERROR:
                errors.append(f"{where}: a story title states a result, not an activity: {t}")
            elif level == "story" and first in STORY_VERBS_WARN:
                warnings.append(f"{where}: story title starts with '{t.split()[0]}', is it a task?")

        description = it.get("description")
        text = to_text(description) if isinstance(description, str) else ""
        if not text:
            errors.append(f"{where}: description is required")
        else:
            low = text.lower()
            missing = [b for b in SKELETON[level] if b.lower() not in low]
            if missing:
                errors.append(f"{where}: description lacks {', '.join(missing)}")
            if level in ("epic", "feature") and re.search(r"<(pre|code)\b", description, re.IGNORECASE):
                warnings.append(f"{where}: no code detail in an {level} description")
            check_self_contained(where, description, document, errors, warnings)
            if repo.ok:
                refs = check_refs(where, text, repo, errors, warnings)
                if level == "task":
                    check_quotes(where, description, refs[0] if refs else None, repo, errors, warnings)

        sources = it.get("sources")
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s.strip() for s in sources):
            errors.append(f"{where}: sources must list where each fact comes from")

        fields = info["fields"]
        for k in LEVEL_KEYS[level]:
            if k in it and k not in fields:
                errors.append(f"{where}: {wtype} has no field for {k} in {tgt['process']}")
            elif k not in it and k in fields:
                errors.append(f"{where}: {k} is required on a {level}")
        if "priority" in it and "priority" in fields:
            p = it["priority"]
            allowed = fields["priority"]["allowed"] or ["1", "2", "3", "4"]
            if isinstance(p, bool) or not isinstance(p, int) or str(p) not in [str(a) for a in allowed]:
                errors.append(f"{where}: priority must be one of {', '.join(map(str, allowed))}")
        if "value_area" in it and "value_area" in fields:
            allowed = fields["value_area"]["allowed"] or ["Architectural", "Business"]
            if it["value_area"] not in allowed:
                errors.append(f"{where}: value_area must be one of {', '.join(allowed)}")
        if level == "story":
            if "risk" in it and "risk" in fields:
                allowed = fields["risk"]["allowed"] or ["1 - High", "2 - Medium", "3 - Low"]
                if it["risk"] not in allowed:
                    errors.append(f"{where}: risk must be one of {', '.join(allowed)}")
            if "story_points" in it:
                sp = it["story_points"]
                if isinstance(sp, bool) or sp not in POINTS:
                    errors.append(f"{where}: story_points must be one of {', '.join(map(str, POINTS))}")
                elif sp == POINTS[-1]:
                    warnings.append(f"{where}: 8 points, consider splitting the story")
            ac = it.get("acceptance_criteria")
            if isinstance(ac, str):
                n = len(re.findall(r"<li\b", ac, re.IGNORECASE))
                if not re.search(r"<ol\b", ac, re.IGNORECASE):
                    errors.append(f"{where}: acceptance_criteria must be a numbered list (<ol>)")
                if not AC_ITEMS[0] <= n <= AC_ITEMS[1]:
                    errors.append(f"{where}: {n} acceptance criteria, {AC_ITEMS[0]} to {AC_ITEMS[1]} expected")
                if banned := sorted({m.lower() for m in AC_BANNED.findall(to_text(ac))}):
                    errors.append(f"{where}: acceptance criteria use banned words: {', '.join(banned)}")
                check_self_contained(f"{where} acceptance criteria", ac, document, errors, warnings)
                if repo.ok:
                    check_refs(where, to_text(ac), repo, errors, warnings)
            elif "acceptance_criteria" in it:
                errors.append(f"{where}: acceptance_criteria must be an HTML string")

    # hierarchy shape and priority derivation
    for key, it in by_key.items():
        level, kids = it.get("level"), children.get(key, [])
        child_level = {"epic": "feature" if levels["feature"]["type"] else "story",
                       "feature": "story", "story": "task"}.get(level)
        if child_level and not kids:
            errors.append(f"{key}: a {level} without any {child_level}")
        if level == "story" and len(kids) > 6:
            warnings.append(f"{key}: {len(kids)} tasks, split the story (2 to 6)")
        if level == "epic" and kids and not 3 <= len(kids) <= 10 and child_level == "feature":
            warnings.append(f"{key}: {len(kids)} features, 3 to 10 expected per epic")
        prios = [k.get("priority") for k in kids if isinstance(k.get("priority"), int)]
        if prios and isinstance(it.get("priority"), int) and it["priority"] != min(prios):
            errors.append(f"{key}: priority {it['priority']}, its most severe child has {min(prios)}")
    epics = [it for it in by_key.values() if it.get("level") == "epic"]
    if len(epics) > 3:
        warnings.append(f"{len(epics)} epics, 1 to 3 expected per document")

    edges = dependencies(by_key, errors, warnings)
    return errors, warnings, {"by_key": by_key, "children": children, "edges": edges}


def lineage(key: str, by_key: dict) -> set[str]:
    out, it = set(), by_key.get(key)
    while it and isinstance(it.get("parent"), str):
        out.add(it["parent"])
        it = by_key.get(it["parent"])
    return out


def find_cycle(edges: list[tuple]) -> list[str] | None:
    graph: dict[str, list[str]] = {}
    for a, b in edges:
        if isinstance(a, str) and isinstance(b, str):
            graph.setdefault(a, []).append(b)
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> list[str] | None:
        state[node] = 1
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if not state.get(nxt) and (cycle := visit(nxt, path + [nxt])):
                return cycle
        state[node] = 2
        return None

    for node in graph:
        if not state.get(node) and (cycle := visit(node, [node])):
            return cycle
    return None


def dependencies(by_key: dict, errors: list, warnings: list) -> list[tuple]:
    """Predecessor / successor links as (predecessor, successor): a key of the plan or an existing id."""
    edges: list[tuple] = []
    for key, it in by_key.items():
        for field, forward in (("predecessors", False), ("successors", True)):
            if field not in it:
                continue
            refs = it[field]
            if not isinstance(refs, list) or not refs:
                errors.append(f"{key}: {field} must be a non-empty list of keys or work item ids")
                continue
            for ref in refs:
                if isinstance(ref, bool) or not isinstance(ref, (str, int)):
                    errors.append(f"{key}: {field} holds {ref!r}, a key of the plan or a work item id is expected")
                elif ref == key:
                    errors.append(f"{key}: an item cannot be its own {field[:-1]}")
                elif isinstance(ref, str) and ref not in by_key:
                    errors.append(f"{key}: {field} names '{ref}', no such key")
                else:
                    edge = (key, ref) if forward else (ref, key)
                    if edge in edges:
                        warnings.append(f"{edge[0]} -> {edge[1]}: dependency given twice")
                    else:
                        edges.append(edge)
    for pred, succ in edges:
        if not (isinstance(pred, str) and isinstance(succ, str)):
            continue
        if pred in lineage(succ, by_key) or succ in lineage(pred, by_key):
            errors.append(f"{pred} -> {succ}: one contains the other, the parent link already orders them")
        elif by_key[pred]["level"] != by_key[succ]["level"]:
            warnings.append(f"{pred} -> {succ}: a {by_key[pred]['level']} before a {by_key[succ]['level']}, "
                            "dependencies usually link items of one level")
    if cycle := find_cycle(edges):
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")
    return edges


def ancestor(key: str, level: str, by_key: dict) -> str | None:
    it = by_key.get(key)
    while it and it.get("level") != level:
        it = by_key.get(it.get("parent")) if isinstance(it.get("parent"), str) else None
    return it.get("key") if it else None


def totals(by_key: dict, tgt: dict) -> dict:
    counts = {}
    for level in LEVELS:
        n = sum(1 for it in by_key.values() if it.get("level") == level)
        if n:
            counts[tgt["levels"][level]["type"]] = n
    per_epic: dict[str, int] = {}
    for it in by_key.values():
        if it.get("level") == "story" and isinstance(it.get("story_points"), int):
            epic = ancestor(it["key"], "epic", by_key) or "(existing parent)"
            title = by_key[epic]["title"] if epic in by_key else epic
            per_epic[title] = per_epic.get(title, 0) + it["story_points"]
    return {"counts": counts, "story_points_per_epic": per_epic, "story_points": sum(per_epic.values())}


def with_children(it: dict, children: dict) -> str:
    """Epic and Feature descriptions end with the list of their child items."""
    description = it.get("description") or ""
    kids = children.get(it.get("key"), [])
    if it.get("level") not in ("epic", "feature") or not kids:
        return description
    rows = "".join(f"<li>{html.escape(k['title'])}</li>" for k in kids)
    return f"{description}<p><strong>Children</strong></p><ul>{rows}</ul>"


def proposal(plan: dict, tgt: dict, shape: dict, sums: dict, sample: str | None) -> str:
    by_key, children, edges = shape["by_key"], shape["children"], shape["edges"]

    def label(ref) -> str:
        if isinstance(ref, int):
            return f"#{ref} (existing)"
        return f"{tgt['levels'][by_key[ref]['level']]['type']} — {by_key[ref]['title']}"

    lines = [f"# Proposal — {tgt['document']}", "",
             f"Azure DevOps: {tgt['org']}/{tgt['project']} (process {tgt['process']})  ",
             f"Area: {plan.get('area') or tgt['project']} · Iteration: {plan.get('iteration') or tgt['project']}", "",
             "## Counts", "", "| Type | Items |", "|---|---|"]
    lines += [f"| {t} | {n} |" for t, n in sums["counts"].items()]
    if sums["story_points_per_epic"]:
        lines += ["", "| Epic | Story points |", "|---|---|"]
        lines += [f"| {e} | {p} |" for e, p in sums["story_points_per_epic"].items()]
        lines += [f"| **Total** | **{sums['story_points']}** |"]
    lines += ["", "## Hierarchy", ""]

    def walk(it: dict, depth: int) -> None:
        wtype = tgt["levels"][it["level"]]["type"]
        facts = [f"P{it['priority']}"] if "priority" in it else []
        if "story_points" in it:
            facts.append(f"{it['story_points']} pts")
        if "risk" in it:
            facts.append(f"Risk {it['risk']}")
        under = f" (under #{it['parent']})" if isinstance(it.get("parent"), int) else ""
        lines.append(f"{'  ' * depth}- **{wtype}** — {it['title']} · {' · '.join(facts)}{under}")
        for kid in children.get(it["key"], []):
            walk(kid, depth + 1)

    for it in by_key.values():
        if not isinstance(it.get("parent"), str):
            walk(it, 0)

    if edges:
        lines += ["", "## Dependencies", "", "Predecessor → successor: the successor waits for the predecessor.", ""]
        lines += [f"- {label(p)} → {label(s)}" for p, s in edges]

    stories = [it for it in by_key.values() if it.get("level") == "story"]
    chosen = by_key.get(sample) if sample else (stories[0] if stories else next(iter(by_key.values())))
    if chosen:
        wtype = tgt["levels"][chosen["level"]]["type"]
        parent = chosen.get("parent")
        parent_txt = (f"#{parent}" if isinstance(parent, int)
                      else f"{tgt['levels'][by_key[parent]['level']]['type']} — {by_key[parent]['title']}"
                      if parent in by_key else "(none)")
        lines += ["", f"## Sample {wtype}", "", "```",
                  f"{'Title':<14} {chosen['title']}", f"{'Parent':<14} {parent_txt}", f"{'State':<14} New"]
        for k, name in (("value_area", "Value Area"), ("story_points", "Story Points"),
                        ("priority", "Priority"), ("risk", "Risk")):
            if k in chosen:
                lines.append(f"{name:<14} {chosen[k]}")
        for name, refs in (("Predecessors", [p for p, s in edges if s == chosen["key"]]),
                           ("Successors", [s for p, s in edges if p == chosen["key"]])):
            if refs:
                lines.append(f"{name:<14} {'; '.join(label(r) for r in refs)}")
        lines += [f"{'Tags':<14} (none)", "```", "", "**Description**", "",
                  to_text(with_children(chosen, children))]
        if chosen.get("acceptance_criteria"):
            lines += ["", "**Acceptance Criteria**", "", to_text(chosen["acceptance_criteria"])]
        lines += ["", "**Sources**", ""] + [f"- {s}" for s in chosen.get("sources", [])]
    return "\n".join(lines).rstrip() + "\n"


def check(document: str, sample: str | None = None) -> dict:
    folder = work_folder(document)
    tgt = load_json(folder / "target.json", "run `target` first")
    plan = load_json(folder / "plan.json", f"write the plan to {(folder / 'plan.json').as_posix()}")
    repo = Repo()
    errors, warnings, shape = validate(plan, tgt, repo)
    if not repo.ok:
        warnings.append("not a git repository: no file:line reference was verified")
    if sample and sample not in shape["by_key"]:
        errors.append(f"--sample {sample}: no such key")
    checked = folder / "checked.json"
    if errors:
        checked.unlink(missing_ok=True)
        raise PlanInvalid(f"{len(errors)} rule(s) broken in plan.json", errors=errors, warnings=warnings)
    sums = totals(shape["by_key"], tgt)
    (folder / "proposal.md").write_text(proposal(plan, tgt, shape, sums, sample), encoding="utf-8")
    write_json(checked, {"fingerprint": fingerprint(folder / "plan.json", folder / "target.json"), "at": now()})
    return {"ok": True, "warnings": warnings, **sums, "dependencies": len(shape["edges"]),
            "proposal_file": (folder / "proposal.md").as_posix(), "plan_file": (folder / "plan.json").as_posix()}


# --- create --------------------------------------------------------------------

def create(document: str, batch: int, dry_run: bool) -> dict:
    folder = work_folder(document)
    tgt = load_json(folder / "target.json", "run `target` first")
    plan = load_json(folder / "plan.json", "no plan to create")
    checked = folder / "checked.json"
    stamp = json.loads(checked.read_text(encoding="utf-8")) if checked.is_file() else {}
    if stamp.get("fingerprint") != fingerprint(folder / "plan.json", folder / "target.json"):
        raise FactoryError("plan.json changed since its last clean check: run `check` and show the proposal "
                           "to the user again before creating anything")
    _, _, shape = validate(plan, tgt, Repo())
    children = shape["children"]
    org, project = tgt["org"], tgt["project"]
    created_file = folder / "created.json"
    created = json.loads(created_file.read_text(encoding="utf-8")) if created_file.is_file() else {}
    values = folder / "values"
    values.mkdir(exist_ok=True)

    def value_file(key: str, name: str, value) -> str:
        path = values / f"{key}.{name}.txt"
        path.write_text(str(value), encoding="utf-8")
        return f"@{path}"

    def parent_id(it: dict):
        p = it.get("parent")
        return p if isinstance(p, int) or p is None else created.get(p, {}).get("id")

    done_now, commands = [], []
    for it in plan["items"]:
        key, level = it["key"], it["level"]
        rec = created.get(key)
        if rec and rec.get("linked"):
            continue
        if len(done_now) >= batch and not rec:
            break
        info = tgt["levels"][level]
        pid = parent_id(it)
        try:
            if not rec:
                cmd = ["az", "boards", "work-item", "create", "--type", info["type"], "--project", project,
                       "--title", value_file(key, "title", it["title"]),
                       "--description", value_file(key, "description", with_children(it, children))]
                if plan.get("area"):
                    cmd += ["--area", plan["area"]]
                if plan.get("iteration"):
                    cmd += ["--iteration", plan["iteration"]]
                pairs = [f"{info['fields'][k]['ref']}={value_file(key, k, it[k])}"
                         for k in LEVEL_KEYS[level] if k in it and k in info["fields"]]
                if pairs:
                    cmd += ["--fields", *pairs]
                if dry_run:
                    commands.append({"key": key, "create": cmd,
                                     "parent": pid or (f"(id of {it['parent']})" if it.get("parent") else None)})
                    done_now.append(key)
                    continue
                out = run(*cmd, "--org", f"https://dev.azure.com/{org}", "-o", "json")
                wid = json.loads(out.stdout)["id"]
                rec = {"id": wid, "url": item_url(org, project, wid), "type": info["type"], "title": it["title"],
                       "parent": pid, "linked": pid is None, "at": now()}
                created[key] = rec
                write_json(created_file, created)
                done_now.append(key)
            if not rec["linked"]:
                az("boards", "work-item", "relation", "add", "--id", str(rec["id"]),
                   "--relation-type", "parent", "--target-id", str(pid), org=org)
                rec["linked"] = True
                write_json(created_file, created)
        except (FactoryError, KeyError, json.JSONDecodeError) as e:
            raise FactoryError(f"{key} ({it['title']}): {e}", failed=key,
                               created_now=[created[k] for k in done_now if k in created],
                               note="nothing after this item was created; run create again to resume") from None

    # dependency links, once every item exists; each one is set on a new item, never on an existing one
    def item_id(ref):
        return ref if isinstance(ref, int) else created.get(ref, {}).get("id")

    links_file = folder / "links.json"
    links = json.loads(links_file.read_text(encoding="utf-8")) if links_file.is_file() else {}
    remaining = [it["key"] for it in plan["items"] if not created.get(it["key"], {}).get("linked")]
    links_now, link_commands = [], []
    if dry_run or not remaining:
        for pred, succ in shape["edges"]:
            name = f"{pred} -> {succ}"
            if links.get(name):
                continue
            if not dry_run and len(done_now) + len(links_now) >= batch:
                break
            on, relation, other = (succ, "predecessor", pred) if isinstance(succ, str) else (pred, "successor", succ)
            cmd = ["az", "boards", "work-item", "relation", "add", "--id", str(item_id(on) or f"(id of {on})"),
                   "--relation-type", relation, "--target-id", str(item_id(other) or f"(id of {other})")]
            if dry_run:
                link_commands.append({"link": name, "add": cmd})
                continue
            try:
                az(*cmd[1:], org=org)
            except FactoryError as e:
                raise FactoryError(f"dependency {name}: {e}", failed=name, links_now=links_now,
                                   created_now=[created[k] for k in done_now if k in created],
                                   note="every item exists; run create again to add the remaining links") from None
            links[name] = {"predecessor": item_id(pred), "successor": item_id(succ), "at": now()}
            write_json(links_file, links)
            links_now.append(name)

    if dry_run:
        return {"dry_run": True, "would_create": len(commands), "commands": commands,
                "would_link": len(link_commands), "link_commands": link_commands}
    links_left = [f"{p} -> {s}" for p, s in shape["edges"] if not links.get(f"{p} -> {s}")]
    out = {"created_now": [created[k] for k in done_now], "created_total": len(plan["items"]) - len(remaining),
           "remaining": len(remaining), "links_now": links_now, "links_remaining": len(links_left),
           "complete": not remaining and not links_left, "created_file": created_file.as_posix()}
    if out["complete"]:
        out["tree"] = [{"level": it["level"], **created[it["key"]]} for it in plan["items"]]
        out["dependencies"] = [links[f"{p} -> {s}"] for p, s in shape["edges"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("target")
    p.add_argument("document")
    p.add_argument("--org")
    p.add_argument("--project")
    p = sub.add_parser("check")
    p.add_argument("document")
    p.add_argument("--sample", help="key of the item shown in full in proposal.md (default: the first story)")
    p = sub.add_parser("create")
    p.add_argument("document")
    p.add_argument("--batch", type=int, default=10, help="new items created by this call (default 10)")
    p.add_argument("--dry-run", action="store_true", help="print the az commands, create nothing")
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    args = ap.parse_args()

    try:
        if args.cmd == "target":
            out = target(args.document, args.org, args.project)
        elif args.cmd == "check":
            out = check(args.document, args.sample)
        else:
            out = create(args.document, max(args.batch, 1), args.dry_run)
    except FactoryError as e:
        print(json.dumps({"error": str(e), **e.extra}, indent=2, ensure_ascii=False))
        return e.code
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
