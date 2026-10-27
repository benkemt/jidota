#!/usr/bin/env python3
"""Construit le graphe de dépendances des tickets à partir de leur bloc YAML.

Usage :
    python ticket_graph.py tickets/                     # graphe + vagues + frontière
    python ticket_graph.py tickets/ --merged T1         # frontière une fois T1 fusionné
    python ticket_graph.py tickets/ --mermaid           # diagramme Mermaid
    python ticket_graph.py tickets/ --json              # sortie machine pour l'orchestrateur

Codes de sortie : 0 = graphe valide, 2 = graphe invalide (cycle, référence inconnue...).
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import yaml

YAML_BLOCK = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)
TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
HUMAN_TAG = "[HUMAN]"


@dataclass
class Ticket:
    id: str
    key: str | None
    title: str
    depends_on: list[str]
    base_commit: str | None
    start_branch: str | None
    touches: list[str]
    path: Path
    deps: set[str] = field(default_factory=set)  # dépendances résolues en ids

    @property
    def human(self) -> bool:
        return HUMAN_TAG in self.title


def parse_ticket(path: Path) -> Ticket:
    text = path.read_text(encoding="utf-8")
    block = YAML_BLOCK.search(text)
    if not block:
        raise ValueError(f"{path.name}: aucun bloc ```yaml``` trouvé")
    meta = yaml.safe_load(block.group(1)) or {}
    title = TITLE.search(text)
    if "id" not in meta:
        raise ValueError(f"{path.name}: champ 'id' manquant")
    return Ticket(
        id=str(meta["id"]),
        key=str(meta["key"]) if meta.get("key") else None,
        title=title.group(1).strip() if title else path.stem,
        depends_on=[str(d) for d in meta.get("depends_on") or []],
        base_commit=str(meta["base_commit"]) if meta.get("base_commit") else None,
        start_branch=meta.get("start_branch"),
        touches=list(meta.get("touches") or []),
        path=path,
    )


def load(folder: Path) -> tuple[dict[str, Ticket], list[str]]:
    """Charge les tickets et résout les dépendances. Retourne (tickets, erreurs)."""
    errors: list[str] = []
    tickets: dict[str, Ticket] = {}
    for p in sorted(folder.glob("*.md")):
        try:
            t = parse_ticket(p)
        except ValueError as e:
            errors.append(str(e))
            continue
        if t.id in tickets:
            errors.append(f"id en double : {t.id}")
        tickets[t.id] = t

    # Une dépendance peut viser l'id local (T1) ou la clé du tracker (ABB-33).
    alias = {t.id: t.id for t in tickets.values()}
    alias |= {t.key: t.id for t in tickets.values() if t.key}

    for t in tickets.values():
        for ref in t.depends_on:
            if ref not in alias:
                errors.append(f"{t.id}: dépend de '{ref}', inconnu dans ce lot")
            elif alias[ref] == t.id:
                errors.append(f"{t.id}: dépend de lui-même")
            else:
                t.deps.add(alias[ref])

    branches = {t.start_branch for t in tickets.values()}
    if len(branches) > 1:
        errors.append(f"start_branch incohérentes : {sorted(map(str, branches))}")
    return tickets, errors


def waves(tickets: dict[str, Ticket]) -> list[list[str]]:
    """Vagues successives : chaque vague ne dépend que des précédentes. Lève CycleError."""
    ts = TopologicalSorter({t.id: t.deps for t in tickets.values()})
    ts.prepare()
    result = []
    while ts.is_active():
        ready = sorted(ts.get_ready())
        result.append(ready)
        ts.done(*ready)
    return result


def frontier(tickets: dict[str, Ticket], merged: set[str], in_progress: set[str]) -> list[str]:
    """Tickets non commencés dont toutes les dépendances sont fusionnées."""
    return sorted(
        t.id for t in tickets.values()
        if t.id not in merged and t.id not in in_progress and t.deps <= merged
    )


def touch_conflicts(tickets: dict[str, Ticket], ids: list[str]) -> list[str]:
    """Fichiers modifiés par plusieurs tickets lancés en parallèle (risque de conflit de merge)."""
    warnings = []
    for a, b in itertools.combinations(ids, 2):
        common = set(tickets[a].touches) & set(tickets[b].touches)
        if common:
            warnings.append(f"{a} et {b} touchent tous les deux {sorted(common)}")
    return warnings


def mermaid(tickets: dict[str, Ticket], merged: set[str], ready: list[str]) -> str:
    lines = ["graph LR"]
    for t in tickets.values():
        label = f"{t.id} {t.key or ''}".strip()
        shape = f'{t.id}[/"{label}"/]' if t.human else f'{t.id}["{label}"]'
        lines.append(f"    {shape}")
    for t in tickets.values():
        for d in sorted(t.deps):
            lines.append(f"    {d} --> {t.id}")
    lines += [
        "    classDef merged fill:#d3f9d8,stroke:#2b8a3e",
        "    classDef ready fill:#fff3bf,stroke:#e67700",
    ]
    if merged:
        lines.append(f"    class {','.join(sorted(merged))} merged")
    if ready:
        lines.append(f"    class {','.join(ready)} ready")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--merged", default="", help="ids fusionnés, séparés par des virgules")
    ap.add_argument("--in-progress", default="", help="ids en cours, séparés par des virgules")
    ap.add_argument("--mermaid", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    tickets, errors = load(args.folder)
    try:
        plan = waves(tickets) if not errors else []
    except CycleError as e:
        errors.append(f"cycle détecté : {' -> '.join(e.args[1])}")
        plan = []
    if errors:
        print("Graphe invalide :", *errors, sep="\n  - ", file=sys.stderr)
        return 2

    merged = {s for s in args.merged.split(",") if s}
    in_progress = {s for s in args.in_progress.split(",") if s}
    ready = frontier(tickets, merged, in_progress)
    agents = [t for t in ready if not tickets[t].human]
    humans = [t for t in ready if tickets[t].human]
    warnings = touch_conflicts(tickets, agents)

    if args.json:
        print(json.dumps({
            "waves": plan,
            "frontier": {"agents": agents, "humans": humans},
            "warnings": warnings,
            "tickets": {t.id: {"key": t.key, "deps": sorted(t.deps), "human": t.human,
                               "file": str(t.path)} for t in tickets.values()},
        }, indent=2, ensure_ascii=False))
    elif args.mermaid:
        print(mermaid(tickets, merged, ready))
    else:
        print("Vagues (ordre topologique) :")
        for i, w in enumerate(plan, 1):
            print(f"  {i}. " + ", ".join(f"{t}{' [HUMAN]' if tickets[t].human else ''}" for t in w))
        print(f"\nFrontière (fusionnés : {sorted(merged) or 'aucun'}) :")
        print(f"  -> sous-agents : {agents or '-'}")
        print(f"  -> humain      : {humans or '-'}")
        for w in warnings:
            print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
