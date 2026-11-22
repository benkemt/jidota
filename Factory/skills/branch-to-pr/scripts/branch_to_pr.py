#!/usr/bin/env python3
"""Facts and delivery of the branch-to-pr skill: a draft pull request from a source branch into a
destination branch, on GitHub or Azure DevOps Repos (found from origin).

`collect` finds the commits of the source that the destination does not have, the code factory
tickets they implement (commit subject `T<n> - <title> (<key>)`), their spec, the scope work items
of the spec, the job files on the factory board, and an open PR of the same two branches. It writes
context.json, plus a copy of each ticket and spec, into a work folder inside the git directory, so
nothing lands in the working tree.

`open` pushes the source branch (never the destination, never with force) and opens the draft PR,
or updates the title and description of the open PR of the same two branches. On Azure DevOps it
also links the scope work items of the specs to the PR.

Reuses factory.py of the code-factory skill (same plugin) for the git helpers, the ticket and spec
loaders and the GitHub / Azure DevOps host. Stdlib only; every command prints JSON on stdout.

Usage:
    python branch_to_pr.py collect <source> <destination>
    python branch_to_pr.py open <source> <destination> --title "..." --body <file> [--dry-run]

Exit codes: 0 ok, 1 error, 2 nothing to propose (no commit, or a merge that changes nothing).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code-factory" / "scripts"))
import factory  # noqa: E402
from factory import ADO_DESCRIPTION_MAX, FactoryError, Host, Ticket, first_yaml, gh_json, git, run  # noqa: E402

SUBJECT = re.compile(r"^(T\d+) - (.+) \(([^()]+)\)$")
ROUND = re.compile(r" - round \d+$")
ADO_MERGED = re.compile(r"^Merged PR \d+: ")
GH_SQUASH = re.compile(r" \(#\d+\)$")
SOURCE_LINE = re.compile(r"^(ADO #(\d+)|https://github\.com/\S+)\s*\((scope|context)\)\s*:?\s*(.*)$", re.IGNORECASE)
SOURCE_URL = re.compile(r"^## ADO #(\d+) — .*?$.*?^- URL: (\S+)", re.MULTILINE | re.DOTALL)
TEST_PATH = re.compile(r"(^|/)(tests?|specs?|__tests__)/|(test|tests|spec)s?\.[^/]+$|[._-](test|tests|spec)\.[^/]+$",
                       re.IGNORECASE)


class NothingToPropose(FactoryError):
    code = 2


# --- branches ----------------------------------------------------------------

def has_ref(ref: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def count(range_: str) -> int:
    return int(git("rev-list", "--count", range_).stdout.strip())


def branches(source: str, destination: str) -> dict:
    """Which refs the PR compares, and whether the source must be pushed first."""
    if source == destination:
        raise FactoryError("source and destination are the same branch")
    fetched = git("fetch", "origin", "--quiet", check=False)
    base = f"origin/{destination}"
    if not has_ref(base):
        raise FactoryError(f"{destination} is not on origin: a PR targets a branch of the remote, "
                           "and this skill never pushes the destination")
    local, remote = f"refs/heads/{source}", f"refs/remotes/origin/{source}"
    if not has_ref(local) and not has_ref(remote):
        raise FactoryError(f"branch {source} found neither locally nor on origin")
    ahead = behind = 0
    if has_ref(local) and has_ref(remote):
        ahead, behind = count(f"{remote}..{local}"), count(f"{local}..{remote}")
        if ahead and behind:
            raise FactoryError(f"{source} and origin/{source} have diverged ({ahead} local, {behind} remote "
                               "commits): integrate origin first, this skill never force-pushes")
    head = local if has_ref(local) else remote
    if behind:
        head = remote
    push = has_ref(local) and (ahead > 0 or not has_ref(remote))
    current = git("branch", "--show-current").stdout.strip()
    dirty = current == source and bool(git("status", "--porcelain", "--untracked-files=no").stdout.strip())
    return {"source": source, "destination": destination, "base": base, "head": head,
            "push": push, "ahead_of_origin": ahead, "behind_origin": behind,
            "uncommitted_on_source": dirty,
            "fetch": "ok" if fetched.returncode == 0 else f"failed: {fetched.stderr.strip()}"}


def commits(base: str, head: str) -> list[dict]:
    out = git("log", "--reverse", "--format=%H%x1f%h%x1f%s", f"{base}..{head}").stdout
    return [dict(zip(("sha", "short", "subject"), line.split("\x1f"))) for line in out.splitlines() if line]


def factory_subjects(subject: str) -> list[str]:
    """The ticket subjects a commit may carry: a factory commit, a round, or a host squash of one.
    `T1 - Title (#36) (#12)` gives both readings; the caller keeps the one a ticket answers to."""
    s = ROUND.sub("", ADO_MERGED.sub("", subject.strip()))
    return list(dict.fromkeys(c for c in (GH_SQUASH.sub("", s), s) if SUBJECT.match(c)))


def merge_preview(base: str, head: str) -> dict:
    """What merging head into base gives, from git merge-tree (git 2.38+), without touching any tree:
    the conflicted files, and whether the result is base itself (the work is already there, as after
    a squash-merge). None when git cannot tell."""
    proc = git("merge-tree", "--write-tree", "--name-only", "--no-messages", base, head, check=False)
    if proc.returncode not in (0, 1):
        return {"conflicts": None, "adds_nothing": None}
    lines = proc.stdout.splitlines()
    tree = lines[0].strip() if lines else ""
    return {"conflicts": [l for l in lines[1:] if l.strip()] if proc.returncode == 1 else [],
            "adds_nothing": proc.returncode == 0 and tree == git("rev-parse", f"{base}^{{tree}}").stdout.strip()}


def ensure_work(source: str, destination: str, refs: dict) -> tuple[list[dict], dict]:
    found = commits(refs["base"], refs["head"])
    preview = merge_preview(refs["base"], refs["head"])
    if not found or preview["adds_nothing"]:
        why = ("every commit of the source is in it" if not found
               else "merging the source changes nothing: its work is already there (squash-merged?)")
        raise NothingToPropose(f"{source} has nothing to propose to origin/{destination}: {why}")
    return found, preview


def diff(base: str, head: str) -> dict:
    rows = git("diff", "--name-status", "-M", f"{base}...{head}").stdout.splitlines()
    files = [{"status": r.split("\t")[0], "path": r.split("\t")[-1]} for r in rows if r.strip()]
    return {"range": f"{base}...{head}", "files": files,
            "tests": [f["path"] for f in files if TEST_PATH.search(f["path"])],
            "stat": git("diff", "--shortstat", f"{base}...{head}").stdout.strip()}


# --- tickets -----------------------------------------------------------------

def board() -> dict:
    """factory/board.json as it is; never created here."""
    path = factory.BOARD
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"jobs": []}


def local_tickets() -> dict[str, Path]:
    """Subject -> file of every local ticket of specs/*/tickets/."""
    out = {}
    for path in sorted(Path("specs").glob("*/tickets/T*.md")):
        try:
            out[factory.ticket_from_file(path).subject] = path
        except FactoryError:
            continue
    return out


def published_url(path: Path) -> str | None:
    state = path.parent.parent / "published.json"
    if not state.is_file():
        return None
    ticket = json.loads(state.read_text(encoding="utf-8")).get("tickets", {}).get(path.stem)
    return ticket["url"] if ticket else None


def spec_factory_repo() -> str | None:
    config = Path.home() / ".claude" / "spec-factory.json"
    return json.loads(config.read_text(encoding="utf-8")).get("repo") if config.is_file() else None


def find_ticket(subject: str, jobs: list[dict], local: dict[str, Path]) -> tuple[str | None, str | None, dict | None, str]:
    """(ref to load, ref to show, board job, how it was found) for a factory commit subject.

    A local ticket is loaded from its file, which keeps the spec folder and its source.md, and
    shown by its GitHub issue once published."""
    job = next((j for j in reversed(jobs) if j["commit"] == subject), None)
    if job:
        return job["ticket"], job["ticket"], job, "factory board"
    if subject in local:
        path = local[subject]
        return factory.local_ref(path), published_url(path) or factory.local_ref(path), None, "local ticket file"
    key = SUBJECT.match(subject).group(3)
    if key.startswith("#") and key[1:].isdigit() and (repo := spec_factory_repo()):
        url = f"https://github.com/{repo}/issues/{key[1:]}"
        return url, url, None, "~/.claude/spec-factory.json repo"
    return None, None, None, "no board job, no local ticket, no GitHub repo for the key"


def spec_folder(spec) -> Path | None:
    """The local specs/<slug>/ of a spec, also for a spec loaded from its GitHub issue."""
    if spec.folder is not None:
        return spec.folder
    for state in Path("specs").glob("*/published.json"):
        if json.loads(state.read_text(encoding="utf-8")).get("spec", {}).get("url") == spec.ref:
            return state.parent
    return None


def github_issue(ref: str) -> dict | None:
    if m := factory.GH_URL.match(ref):
        return {"repo": f"{m.group(1)}/{m.group(2)}", "number": int(m.group(3)), "url": ref}
    return None


def spec_sources(spec_raw: str, folder: Path | None) -> list[dict]:
    urls = {}
    if folder and (folder / "source.md").is_file():
        urls = dict(SOURCE_URL.findall((folder / "source.md").read_text(encoding="utf-8")))
    out = []
    for line in first_yaml(spec_raw).get("sources") or []:
        if m := SOURCE_LINE.match(line):
            ado = m.group(2)
            out.append({"ref": m.group(1), "kind": "ado" if ado else "github", "id": int(ado) if ado else None,
                        "role": m.group(3).lower(), "title": m.group(4).strip(),
                        "url": urls.get(ado) if ado else m.group(1)})
    return out


def heading(text: str, name: str) -> str | None:
    """Body of a `### <name>` section of a ticket."""
    m = re.search(rf"^###\s+{re.escape(name)}\s*$(.*?)(?=^#{{1,3}}\s|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


def describe(ticket: Ticket, ref: str, job: dict | None, found: str, on_branch: set[str], folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{ticket.spec.slug}-{ticket.id}"
    (folder / f"{stem}-ticket.md").write_text(ticket.raw, encoding="utf-8")
    (folder / f"{ticket.spec.slug}-spec.md").write_text(ticket.spec.raw, encoding="utf-8")
    job_folder = factory.JOBS / job["id"] if job else None
    job_files = {}
    if job_folder:
        job_files = {f: (job_folder / f).resolve().as_posix() for f in factory.job_files(job["id"])}
    siblings = []
    try:
        siblings = [{"id": t.id, "title": t.title, "ref": t.ref, "human": t.human, "state": t.state,
                     "on_branch": t.subject in on_branch} for t in ticket.spec.tickets if t.id != ticket.id]
    except FactoryError as e:
        siblings = [{"error": str(e)}]
    return {
        "id": ticket.id, "key": ticket.key, "title": ticket.title, "subject": ticket.subject, "ref": ref,
        "github": github_issue(ref), "found_by": found, "human": ticket.human, "state": ticket.state,
        "done_when": heading(ticket.raw, "Done when"), "how_to_check": heading(ticket.raw, "How to check"),
        "out_of_scope": heading(ticket.raw, "Out of scope"),
        "spec": {"ref": ticket.spec.ref, "title": ticket.spec.title, "slug": ticket.spec.slug,
                 "sources": spec_sources(ticket.spec.raw, spec_folder(ticket.spec)),
                 "other_tickets": siblings},
        "copies": {"ticket": (folder / f"{stem}-ticket.md").resolve().as_posix(),
                   "spec": (folder / f"{ticket.spec.slug}-spec.md").resolve().as_posix()},
        "job": {"id": job["id"], "stage": job["stage"], "branch": job["branch"], "rounds": job["rounds"],
                "pr": job.get("pr"), "files": job_files} if job else None,
    }


# --- host --------------------------------------------------------------------

def open_pr(host: Host, source: str, destination: str) -> dict | None:
    """The open PR of these two branches, with its draft flag and description."""
    if host.kind == "github":
        prs = json.loads(run("gh", "pr", "list", "-R", host.repo, "--head", source, "--base", destination,
                             "--state", "open", "--json", "number,url,isDraft,title,body").stdout or "[]")
        return ({"number": prs[0]["number"], "url": prs[0]["url"], "draft": prs[0]["isDraft"],
                 "title": prs[0]["title"], "body": prs[0]["body"]} if prs else None)
    prs = json.loads(run(*host._az("list", "--project", host.project, "--repository", host.repo,
                                   "--source-branch", source, "--target-branch", destination,
                                   "--status", "active")).stdout or "[]")
    if not prs:
        return None
    pr = prs[0]
    return {"number": pr["pullRequestId"], "url": host._ado_url(pr["pullRequestId"]), "draft": pr.get("isDraft"),
            "title": pr.get("title"), "body": pr.get("description") or ""}


def work_folder(source: str) -> Path:
    common = Path(git("rev-parse", "--git-common-dir").stdout.strip())
    return (common / "branch-to-pr" / re.sub(r"[^\w.-]+", "-", source)).resolve()


# --- commands ----------------------------------------------------------------

def collect(source: str, destination: str) -> dict:
    host = Host.from_origin()
    refs = branches(source, destination)
    found_commits, preview = ensure_work(source, destination, refs)

    folder = work_folder(source)
    jobs = board()["jobs"]
    local = local_tickets()
    known = {j["commit"] for j in jobs} | set(local)
    # A factory/<job-id> branch is that job's ticket, whatever its commit subjects became.
    branch_job = next((j for j in jobs if j["branch"] == source), None)
    by_subject: dict[str, list[dict]] = {branch_job["commit"]: []} if branch_job else {}
    for c in found_commits:
        if readings := factory_subjects(c["subject"]):
            subject = next((r for r in readings if r in known), readings[0])
        elif branch_job:
            subject = branch_job["commit"]
        else:
            continue
        by_subject.setdefault(subject, []).append(c)

    tickets, unresolved = [], []
    for subject, its_commits in by_subject.items():
        load, ref, job, how = find_ticket(subject, jobs, local)
        if load is None:
            unresolved.append({"subject": subject, "reason": how, "commits": [c["short"] for c in its_commits]})
            continue
        try:
            ticket = factory.load_ticket(load)
        except FactoryError as e:
            unresolved.append({"subject": subject, "reason": f"{ref}: {e}", "commits": [c["short"] for c in its_commits]})
            continue
        if ticket.subject != subject:
            unresolved.append({"subject": subject, "reason": f"{ref} has the subject '{ticket.subject}'",
                               "commits": [c["short"] for c in its_commits]})
            continue
        entry = describe(ticket, ref, job, how, set(by_subject), folder)
        entry["commits"] = [c["short"] for c in its_commits]
        tickets.append(entry)

    in_destination = {r for x in git("log", "--format=%s", refs["base"]).stdout.splitlines()
                      for r in factory_subjects(x)}
    for t in tickets:
        t["in_destination"] = t["subject"] in in_destination
    claimed = {s for e in tickets for s in e["commits"]}
    ado = {}
    for t in tickets:
        for s in t["spec"]["sources"]:
            if s["kind"] == "ado" and s["role"] == "scope":
                ado.setdefault(s["id"], s)
    pr = open_pr(host, source, destination)
    context = {
        "host": {"kind": host.kind, "repo": host.repo, "org": host.org, "project": host.project},
        "branches": refs, "commits": found_commits,
        "commits_without_ticket": [c for c in found_commits if c["short"] not in claimed],
        "tickets": tickets, "unresolved": unresolved, "ado_scope": list(ado.values()),
        "diff": diff(refs["base"], refs["head"]), "conflicts": preview["conflicts"],
        "open_pr": pr, "work_folder": folder.as_posix(), "body_file": (folder / "body.md").as_posix(),
        "description_max": ADO_DESCRIPTION_MAX if host.kind == "ado" else None,
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    context["context_file"] = (folder / "context.json").as_posix()
    if pr:
        context["open_pr"] = {k: v for k, v in pr.items() if k != "body"} | {"body_chars": len(pr["body"] or "")}
    return context


def open_cmd(source: str, destination: str, title: str, body_file: str, dry_run: bool) -> dict:
    host = Host.from_origin()
    refs = branches(source, destination)
    ensure_work(source, destination, refs)
    body = Path(body_file).read_text(encoding="utf-8")
    if not title.strip() or not body.strip():
        raise FactoryError("empty title or description")
    if host.kind == "ado" and len(body) > ADO_DESCRIPTION_MAX:
        raise FactoryError(f"the description has {len(body)} characters, Azure DevOps keeps {ADO_DESCRIPTION_MAX}: "
                           "shorten it", chars=len(body))
    context_file = work_folder(source) / "context.json"
    ado = json.loads(context_file.read_text(encoding="utf-8")).get("ado_scope", []) if context_file.is_file() else []
    work_items = [str(s["id"]) for s in ado] if host.kind == "ado" else []

    push = ["git", "push", "-u", "origin", f"{source}:{source}"] if refs["push"] else None
    existing = open_pr(host, source, destination)
    if dry_run:
        pr = (host.update_cmd(existing["number"], title, body_file) if existing
              else host.create_cmd(source, destination, title, body_file))
        return {"dry_run": True, "host": host.kind, "push": push, "pr": pr, "update": bool(existing),
                "work_items": work_items}

    if push:
        pushed = git(*push[1:], check=False)
        if pushed.returncode != 0:
            raise FactoryError(f"push of {source} rejected: {pushed.stderr.strip() or pushed.stdout.strip()}")
    if existing:
        host.update(existing["number"], title, body_file)
        pr = existing
    else:
        pr = host.create(source, destination, title, body_file)
    linked, link_error = [], None
    if work_items:
        added = run(*host._az("work-item", "add", "--id", str(pr["number"]), "--work-items", *work_items),
                    check=False)
        if added.returncode == 0:
            linked = work_items
        else:
            link_error = added.stderr.strip() or added.stdout.strip()
    return {"host": host.kind, "pr": {"number": pr["number"], "url": pr["url"]}, "updated": bool(existing),
            "draft": existing["draft"] if existing else True, "pushed": source if push else None,
            "work_items_linked": linked, "work_items_error": link_error}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect")
    p.add_argument("source")
    p.add_argument("destination")
    p = sub.add_parser("open")
    p.add_argument("source")
    p.add_argument("destination")
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True, help="markdown file holding the PR description")
    p.add_argument("--dry-run", action="store_true", help="print the push and the gh / az command, change nothing")
    sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()

    try:
        if git("rev-parse", "--show-toplevel", check=False).returncode != 0:
            raise FactoryError("not a git repository: run from the root of the code repository")
        if args.cmd == "collect":
            out = collect(args.source, args.destination)
        else:
            out = open_cmd(args.source, args.destination, args.title, args.body, args.dry_run)
    except FactoryError as e:
        print(json.dumps({"error": str(e), **e.extra}, indent=2, ensure_ascii=False))
        return e.code
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
