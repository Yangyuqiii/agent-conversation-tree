#!/usr/bin/env python3
"""Conversation-tree graph store: points, forks, and merge records."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extract_points import extract_points

SCHEMA_VERSION = 1
KINDS = ("session", "turn", "point", "fork", "merge")
STATUSES = ("open", "forked", "discussing", "merged", "abandoned")
MERGE_MODES = ("summary", "full", "selective")
ORIGINS = ("extracted", "user-confirmed")


def store_dir() -> Path:
    override = os.environ.get("CONVERSATION_TREE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return (codex_home / "conversation-trees").resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def graph_path(root_thread_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in root_thread_id.strip())
    if not safe:
        raise ValueError("root thread id is empty")
    return store_dir() / f"{safe}.json"


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_graph(root_thread_id: str) -> dict[str, Any]:
    path = graph_path(root_thread_id)
    if not path.is_file():
        raise FileNotFoundError(f"graph not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("graph file is not an object")
    return payload


def save_graph(graph: dict[str, Any]) -> Path:
    graph["updatedAt"] = now_iso()
    path = graph_path(str(graph["rootThreadId"]))
    atomic_write(path, graph)
    return path


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def new_node(
    *,
    node_id: str,
    parent_id: str | None,
    kind: str,
    title: str,
    excerpt: str = "",
    status: str = "open",
    codex_thread_id: str | None = None,
    source: dict[str, Any] | None = None,
    merge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    return {
        "id": node_id,
        "parentId": parent_id,
        "kind": kind,
        "title": title,
        "excerpt": excerpt,
        "status": status,
        "codexThreadId": codex_thread_id,
        "source": source,
        "merge": merge,
        "createdAt": now_iso(),
    }


def nodes_by_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in graph.get("nodes", [])}


def children_of(graph: dict[str, Any], parent_id: str | None) -> list[dict[str, Any]]:
    return [node for node in graph.get("nodes", []) if node.get("parentId") == parent_id]


def find_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = nodes_by_id(graph).get(node_id)
    if node is None:
        raise KeyError(f"node not found: {node_id}")
    return node


def next_index(graph: dict[str, Any], prefix: str) -> int:
    highest = 0
    for node in graph.get("nodes", []):
        node_id = str(node.get("id", ""))
        if not node_id.startswith(prefix):
            continue
        suffix = node_id[len(prefix) :].split("-")[0]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest + 1


def resolve_point(graph: dict[str, Any], selector: str) -> dict[str, Any]:
    selector = (selector or "").strip()
    if not selector:
        raise KeyError("point selector is empty")
    by_id = nodes_by_id(graph)
    if selector in by_id and by_id[selector]["kind"] == "point":
        return by_id[selector]
    compact = selector.replace("第", "").replace("点", "").replace("point-", "")
    if compact.isdigit():
        index = int(compact)
        points = [node for node in graph["nodes"] if node["kind"] == "point"]
        exact = [node for node in points if (node.get("source") or {}).get("pointIndex") == index]
        if len(exact) == 1:
            return exact[0]
        if exact:
            return exact[-1]
        numbered = [node for node in points if node["id"].endswith(f"-{index}")]
        if numbered:
            return numbered[-1]
    lowered = selector.lower()
    titled = [
        node
        for node in graph["nodes"]
        if node["kind"] == "point" and lowered in str(node.get("title", "")).lower()
    ]
    if len(titled) == 1:
        return titled[0]
    raise KeyError(f"cannot resolve point: {selector}")


def init_graph(root_thread_id: str, title: str, thread_id: str | None = None) -> dict[str, Any]:
    path = graph_path(root_thread_id)
    if path.is_file():
        graph = load_graph(root_thread_id)
        if title:
            session = find_node(graph, "session")
            session["title"] = title
            save_graph(graph)
        return graph
    created = now_iso()
    graph = {
        "schemaVersion": SCHEMA_VERSION,
        "rootThreadId": root_thread_id,
        "title": title or "Untitled session",
        "createdAt": created,
        "updatedAt": created,
        "nodes": [
            new_node(
                node_id="session",
                parent_id=None,
                kind="session",
                title=title or "Untitled session",
                status="open",
                codex_thread_id=thread_id or root_thread_id,
            )
        ],
    }
    save_graph(graph)
    return graph


def add_turn(
    graph: dict[str, Any],
    *,
    role: str,
    title: str,
    excerpt: str = "",
    message_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    index = next_index(graph, "turn-")
    node_id = turn_id or f"turn-{index}"
    if node_id in nodes_by_id(graph):
        return find_node(graph, node_id)
    node = new_node(
        node_id=node_id,
        parent_id="session",
        kind="turn",
        title=title or f"Turn {index}",
        excerpt=excerpt,
        status="open",
        source={"role": role, "messageId": message_id, "turnIndex": index},
    )
    graph["nodes"].append(node)
    return node


def normalize_ingest_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for point in points:
        raw_index = point.get("index")
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"point index must be a positive integer: {raw_index!r}") from exc
        if index < 1:
            raise ValueError(f"point index must be a positive integer starting at 1, got {index}")
        title = str(point.get("title") or "").strip()
        if not title:
            raise ValueError(f"point {index} has an empty title")
        excerpt = str(point.get("excerpt") or "").strip()
        heading = str(point.get("heading") or title).strip() or title
        normalized.append(
            {
                "index": index,
                "title": title,
                "excerpt": excerpt or title,
                "heading": heading,
            }
        )
    return normalized


def ingest_points(
    graph: dict[str, Any],
    *,
    text: str | None = None,
    points: list[dict[str, Any]] | None = None,
    turn_id: str | None = None,
    message_id: str | None = None,
    turn_title: str | None = None,
    origin: str | None = None,
) -> list[dict[str, Any]]:
    parsed = points if points is not None else extract_points(text or "")
    if not parsed:
        return []
    if origin is None:
        origin = "extracted"
    if origin not in ORIGINS:
        raise ValueError(f"unknown origin: {origin}")
    parsed = normalize_ingest_points(parsed)
    turn = None
    if turn_id:
        try:
            turn = find_node(graph, turn_id)
        except KeyError:
            turn = None
    if turn is None:
        turn = add_turn(
            graph,
            role="assistant",
            title=turn_title or "Assistant answer",
            excerpt=(parsed[0].get("excerpt") if parsed else "") or "",
            message_id=message_id,
        )
    created: list[dict[str, Any]] = []
    turn_index = (turn.get("source") or {}).get("turnIndex") or next_index(graph, "turn-")
    existing = {
        (node.get("source") or {}).get("pointIndex"): node
        for node in children_of(graph, turn["id"])
        if node["kind"] == "point"
    }
    for point in parsed:
        index = int(point["index"])
        source = {
            "messageId": message_id,
            "pointIndex": index,
            "heading": point.get("heading") or point.get("title"),
            "turnId": turn["id"],
            "origin": origin,
        }
        if index in existing:
            node = existing[index]
            node["title"] = point.get("title") or node["title"]
            node["excerpt"] = point.get("excerpt") or node["excerpt"]
            node["source"] = {**(node.get("source") or {}), **source}
            created.append(node)
            continue
        node_id = f"point-{turn_index}-{index}"
        node = new_node(
            node_id=node_id,
            parent_id=turn["id"],
            kind="point",
            title=str(point.get("title") or f"Point {index}"),
            excerpt=str(point.get("excerpt") or ""),
            status="open",
            source=source,
        )
        graph["nodes"].append(node)
        created.append(node)
    return created


def fork_point(
    graph: dict[str, Any],
    *,
    point_selector: str,
    child_thread_id: str,
    title: str | None = None,
    status: str = "discussing",
) -> dict[str, Any]:
    point = resolve_point(graph, point_selector)
    fork_id = f"fork-{point['id']}"
    fork_title = title or f"{graph.get('title') or 'Session'} · {point['title']}"
    existing = nodes_by_id(graph).get(fork_id)
    if existing:
        existing["codexThreadId"] = child_thread_id
        existing["title"] = fork_title
        existing["status"] = status if status in STATUSES else "discussing"
        point["status"] = "forked"
        point["codexThreadId"] = child_thread_id
        return existing
    fork = new_node(
        node_id=fork_id,
        parent_id=point["id"],
        kind="fork",
        title=fork_title,
        excerpt=point.get("excerpt") or "",
        status=status if status in STATUSES else "discussing",
        codex_thread_id=child_thread_id,
        source={"pointId": point["id"], "pointIndex": (point.get("source") or {}).get("pointIndex")},
    )
    graph["nodes"].append(fork)
    point["status"] = "forked"
    point["codexThreadId"] = child_thread_id
    return fork


def format_merge_block(
    *,
    title: str,
    point_id: str,
    mode: str,
    source_thread: str | None,
    body: str,
    source_node: str | None = None,
) -> str:
    if mode not in MERGE_MODES:
        raise ValueError(f"unknown merge mode: {mode}")
    lines = [
        f"## Merged from: {title} ({point_id})",
        f"mode: {mode}",
        f"source_thread: {source_thread or ''}".rstrip(),
        f"source_node: {source_node or ''}".rstrip(),
        "",
    ]
    content = (body or "").strip()
    if mode == "full":
        lines.append("<details>")
        lines.append(f"<summary>Full child transcript: {title}</summary>")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("</details>")
    else:
        lines.append(content)
    return "\n".join(lines).strip() + "\n"


def merge_point(
    graph: dict[str, Any],
    *,
    point_selector: str,
    mode: str,
    body: str,
    source_thread_id: str | None = None,
    title: str | None = None,
) -> tuple[dict[str, Any], str]:
    if mode not in MERGE_MODES:
        raise ValueError(f"unknown merge mode: {mode}")
    point = resolve_point(graph, point_selector)
    forks = [node for node in children_of(graph, point["id"]) if node["kind"] == "fork"]
    fork = forks[-1] if forks else None
    merge_count = len([node for node in graph["nodes"] if str(node.get("id", "")).startswith(f"merge-{point['id']}")])
    merge_id = f"merge-{point['id']}-{merge_count + 1}"
    heading = title or point["title"]
    source_thread = source_thread_id or (fork or {}).get("codexThreadId") or point.get("codexThreadId")
    message = format_merge_block(
        title=heading,
        point_id=point["id"],
        mode=mode,
        source_thread=source_thread,
        body=body,
        source_node=(fork or {}).get("id"),
    )
    excerpt = body.strip().splitlines()[0][:240] if body.strip() else heading
    merge_node = new_node(
        node_id=merge_id,
        parent_id=point["id"],
        kind="merge",
        title=f"Merge · {heading}",
        excerpt=excerpt,
        status="merged",
        source={"pointId": point["id"], "forkId": (fork or {}).get("id")},
        merge={
            "mode": mode,
            "at": now_iso(),
            "sourceThreadId": source_thread,
            "excerpt": excerpt,
            "payload": message,
        },
    )
    graph["nodes"].append(merge_node)
    point["status"] = "merged"
    if fork:
        fork["status"] = "merged"
    return merge_node, message


def abandon_point(graph: dict[str, Any], point_selector: str) -> dict[str, Any]:
    point = resolve_point(graph, point_selector)
    point["status"] = "abandoned"
    for node in children_of(graph, point["id"]):
        if node["kind"] == "fork" and node.get("status") != "merged":
            node["status"] = "abandoned"
    return point


def set_status(graph: dict[str, Any], node_id: str, status: str) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    node = find_node(graph, node_id)
    node["status"] = status
    return node


def opening_message(point: dict[str, Any], question: str | None = None) -> str:
    quoted = point.get("excerpt") or point.get("title") or ""
    lines = [
        "Focus only on this point from the parent answer. Do not synthesize unrelated points.",
        "",
        f"Point id: {point['id']}",
        f"Point title: {point.get('title')}",
        "",
        "Quoted point:",
        quoted,
    ]
    if question:
        lines.extend(["", "User question:", question.strip()])
    lines.extend(
        [
            "",
            "Stay on this point until the user asks to merge back to the parent thread.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def require(args: argparse.Namespace, field: str) -> str:
    value = getattr(args, field, None)
    if not value:
        raise SystemExit(f"missing required argument: --{field.replace('_', '-')}")
    return str(value)


def read_text_arg(path_value: str | None, inline: str | None) -> str:
    if path_value:
        if path_value == "-":
            return sys.stdin.read()
        return Path(path_value).read_text(encoding="utf-8")
    return inline or ""


def cmd_init(args: argparse.Namespace) -> int:
    graph = init_graph(require(args, "root_thread_id"), args.title or "", args.thread_id)
    emit({"ok": True, "graphPath": str(graph_path(graph["rootThreadId"])), "graph": graph})
    return 0


def cmd_add_turn(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    node = add_turn(
        graph,
        role=args.role,
        title=args.title or "",
        excerpt=args.excerpt or "",
        message_id=args.message_id,
        turn_id=args.turn_id,
    )
    path = save_graph(graph)
    emit({"ok": True, "graphPath": str(path), "node": node})
    return 0


def cmd_ingest_points(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    points = None
    if args.points_json:
        raw = json.loads(Path(args.points_json).read_text(encoding="utf-8"))
        points = raw.get("points", raw) if isinstance(raw, dict) else raw
        if not isinstance(points, list):
            raise ValueError("points JSON must be a list or an object with a points array")
    text = read_text_arg(args.text_file, args.text)
    origin = args.origin
    if origin is None:
        origin = "user-confirmed" if args.points_json else "extracted"
    created = ingest_points(
        graph,
        text=text,
        points=points,
        turn_id=args.turn_id,
        message_id=args.message_id,
        turn_title=args.turn_title,
        origin=origin,
    )
    path = save_graph(graph)
    emit({"ok": True, "graphPath": str(path), "count": len(created), "nodes": created})
    return 0 if created else 2


def cmd_fork(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    point = resolve_point(graph, require(args, "point_id"))
    fork = fork_point(
        graph,
        point_selector=point["id"],
        child_thread_id=require(args, "child_thread_id"),
        title=args.title,
        status=args.status or "discussing",
    )
    path = save_graph(graph)
    emit(
        {
            "ok": True,
            "graphPath": str(path),
            "point": point,
            "node": fork,
            "openingMessage": opening_message(point, args.question),
            "suggestedTitle": fork["title"],
        }
    )
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    body = read_text_arg(args.body_file, args.body)
    if not body.strip():
        raise SystemExit("merge body is empty; pass --body or --body-file")
    node, message = merge_point(
        graph,
        point_selector=require(args, "point_id"),
        mode=require(args, "mode"),
        body=body,
        source_thread_id=args.source_thread_id,
        title=args.title,
    )
    path = save_graph(graph)
    emit({"ok": True, "graphPath": str(path), "node": node, "mergeMessage": message})
    return 0


def cmd_abandon(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    node = abandon_point(graph, require(args, "point_id"))
    path = save_graph(graph)
    emit({"ok": True, "graphPath": str(path), "node": node})
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    node = set_status(graph, require(args, "node_id"), require(args, "status"))
    path = save_graph(graph)
    emit({"ok": True, "graphPath": str(path), "node": node})
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    if args.node_id:
        emit({"ok": True, "node": find_node(graph, args.node_id), "graphPath": str(graph_path(graph["rootThreadId"]))})
        return 0
    emit({"ok": True, "graph": graph, "graphPath": str(graph_path(graph["rootThreadId"]))})
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    emit({"ok": True, "graphPath": str(graph_path(require(args, "root_thread_id")))})
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    directory = store_dir()
    trees = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            trees.append(
                {
                    "path": str(path),
                    "rootThreadId": payload.get("rootThreadId"),
                    "title": payload.get("title"),
                    "updatedAt": payload.get("updatedAt"),
                }
            )
    emit({"ok": True, "storeDir": str(directory), "trees": trees})
    return 0


def cmd_opening(args: argparse.Namespace) -> int:
    graph = load_graph(require(args, "root_thread_id"))
    point = resolve_point(graph, require(args, "point_id"))
    emit({"ok": True, "point": point, "openingMessage": opening_message(point, args.question)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read and update conversation-tree graphs.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_root(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--root-thread-id", required=True)

    init = sub.add_parser("init", help="Create or reuse a graph for a root thread")
    add_root(init)
    init.add_argument("--title", default="")
    init.add_argument("--thread-id")
    init.set_defaults(func=cmd_init)

    add_turn = sub.add_parser("add-turn", help="Append a turn node under the session")
    add_root(add_turn)
    add_turn.add_argument("--role", choices=("user", "assistant"), default="assistant")
    add_turn.add_argument("--title", default="")
    add_turn.add_argument("--excerpt", default="")
    add_turn.add_argument("--message-id")
    add_turn.add_argument("--turn-id")
    add_turn.set_defaults(func=cmd_add_turn)

    ingest = sub.add_parser("ingest-points", help="Extract or insert forkable points")
    add_root(ingest)
    ingest.add_argument("--turn-id")
    ingest.add_argument("--turn-title")
    ingest.add_argument("--message-id")
    ingest.add_argument("--text")
    ingest.add_argument("--text-file")
    ingest.add_argument("--points-json")
    ingest.add_argument("--origin", choices=ORIGINS)
    ingest.set_defaults(func=cmd_ingest_points)

    fork = sub.add_parser("fork", help="Bind a child Codex thread to a point")
    add_root(fork)
    fork.add_argument("--point-id", required=True)
    fork.add_argument("--child-thread-id", required=True)
    fork.add_argument("--title")
    fork.add_argument("--question")
    fork.add_argument("--status", choices=STATUSES, default="discussing")
    fork.set_defaults(func=cmd_fork)

    merge = sub.add_parser("merge", help="Record a merge and print the parent message")
    add_root(merge)
    merge.add_argument("--point-id", required=True)
    merge.add_argument("--mode", required=True, choices=MERGE_MODES)
    merge.add_argument("--body")
    merge.add_argument("--body-file")
    merge.add_argument("--source-thread-id")
    merge.add_argument("--title")
    merge.set_defaults(func=cmd_merge)

    abandon = sub.add_parser("abandon", help="Mark a point/fork abandoned")
    add_root(abandon)
    abandon.add_argument("--point-id", required=True)
    abandon.set_defaults(func=cmd_abandon)

    status = sub.add_parser("set-status", help="Set a node status")
    add_root(status)
    status.add_argument("--node-id", required=True)
    status.add_argument("--status", required=True, choices=STATUSES)
    status.set_defaults(func=cmd_set_status)

    get = sub.add_parser("get", help="Print a graph or one node")
    add_root(get)
    get.add_argument("--node-id")
    get.set_defaults(func=cmd_get)

    path = sub.add_parser("path", help="Print the graph file path")
    add_root(path)
    path.set_defaults(func=cmd_path)

    listing = sub.add_parser("list", help="List stored graphs")
    listing.set_defaults(func=cmd_list)

    opening = sub.add_parser("opening", help="Print the child-thread opening message")
    add_root(opening)
    opening.add_argument("--point-id", required=True)
    opening.add_argument("--question")
    opening.set_defaults(func=cmd_opening)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as error:
        emit({"ok": False, "error": str(error)})
        return 1
    except (KeyError, ValueError) as error:
        emit({"ok": False, "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
