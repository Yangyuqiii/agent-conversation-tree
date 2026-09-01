#!/usr/bin/env python3
"""Render a conversation-tree graph as a Visualize HTML fragment."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from graph import graph_path, load_graph, children_of, store_dir

STATUS_LABELS = {
    "open": "可讨论",
    "forked": "已分叉",
    "discussing": "讨论中",
    "merged": "已合并",
    "abandoned": "已放弃",
}

KIND_LABELS = {
    "session": "会话",
    "turn": "回合",
    "point": "要点",
    "fork": "子进程",
    "merge": "合并",
}


def attr(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def text(value: str) -> str:
    return html.escape(str(value or ""))


def follow_up_prompt(node: dict, action: str) -> str:
    node_id = node.get("id", "")
    title = node.get("title", "")
    thread_id = node.get("codexThreadId") or ""
    if action == "fork":
        return (
            f"使用 $conversation-tree，fork 要点「{title}」（id: {node_id}）。"
            "只讨论这一点，不要综合其它要点。"
        )
    if action == "open":
        return (
            f"使用 $conversation-tree，打开要点「{title}」对应的 Codex 任务"
            f"（node {node_id}, thread {thread_id}）。"
        )
    if action == "merge":
        return (
            f"使用 $conversation-tree，将要点「{title}」（id: {node_id}）合并回主进程。"
            "若我还没选模式，先问我选 summary、full 还是 selective。"
        )
    return f"使用 $conversation-tree，处理节点 {node_id}。"


def follow_up_title(action: str, title: str) -> str:
    labels = {"fork": "Fork", "open": "打开任务", "merge": "合并回主线"}
    return f"{labels.get(action, action)} {title}".strip()


BUTTON_LABELS = {"fork": "Fork", "open": "打开", "merge": "合并"}


def actions_for(node: dict) -> list[str]:
    kind = node.get("kind")
    status = node.get("status")
    if kind == "point" and status in {"open", "abandoned"}:
        return ["fork"]
    if kind in {"point", "fork"} and status in {"forked", "discussing", "merged"}:
        actions = ["open"]
        if status != "abandoned":
            actions.append("merge")
        return actions
    return []


def render_actions(node: dict) -> str:
    buttons = []
    for action in actions_for(node):
        label = BUTTON_LABELS[action]
        buttons.append(
            "<button type='button' class='ct-action'"
            f" data-action='{attr(action)}'"
            f" data-prompt='{attr(follow_up_prompt(node, action))}'"
            f" data-title='{attr(follow_up_title(action, node.get('title') or ''))}'>"
            f"{text(label)}</button>"
        )
    if not buttons:
        return ""
    return "<span class='ct-actions'>" + "".join(buttons) + "</span>"


def render_node(graph: dict, node: dict) -> str:
    kind = node.get("kind", "")
    status = node.get("status", "open")
    status_label = STATUS_LABELS.get(status, status)
    kind_label = KIND_LABELS.get(kind, kind)
    excerpt = node.get("excerpt") or ""
    excerpt_html = f"<p class='ct-excerpt'>{text(excerpt)}</p>" if excerpt and kind in {"point", "fork", "merge"} else ""
    origin = (node.get("source") or {}).get("origin")
    origin_html = ""
    if kind == "point" and origin == "user-confirmed":
        origin_html = "<span class='ct-origin'>用户指定</span>"
    children = children_of(graph, node["id"])
    child_html = ""
    if children:
        child_html = "<ol class='ct-children'>" + "".join(
            f"<li>{render_node(graph, child)}</li>" for child in children
        ) + "</ol>"
    return (
        f"<article class='ct-node ct-{attr(kind)} ct-status-{attr(status)}' data-node-id='{attr(node['id'])}'>"
        "<div class='ct-row'>"
        f"<span class='ct-kind'>{text(kind_label)}</span>"
        f"<span class='ct-title'>{text(node.get('title') or node['id'])}</span>"
        f"{origin_html}"
        f"<span class='ct-status'>{text(status_label)}</span>"
        f"{render_actions(node)}"
        "</div>"
        f"{excerpt_html}"
        f"{child_html}"
        "</article>"
    )


def render_fragment(graph: dict) -> str:
    session = next(node for node in graph["nodes"] if node.get("kind") == "session")
    root_id = "conversation-tree-" + "".join(
        ch if ch.isalnum() else "-" for ch in str(graph.get("rootThreadId", "root"))
    )
    tree = render_node(graph, session)
    return f"""<div id="{attr(root_id)}" class="conversation-tree" data-root-thread="{attr(graph.get('rootThreadId') or '')}">
<style>
#{attr(root_id)}.conversation-tree {{
  color: var(--foreground, CanvasText);
  font-family: inherit;
  font-size: var(--font-size-base, 14px);
  line-height: 1.45;
}}
#{attr(root_id)} .ct-node {{
  margin: 0;
}}
#{attr(root_id)} .ct-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.6rem;
  align-items: baseline;
}}
#{attr(root_id)} .ct-kind,
#{attr(root_id)} .ct-status,
#{attr(root_id)} .ct-origin,
#{attr(root_id)} .ct-excerpt {{
  color: var(--muted-foreground, GrayText);
  font-size: 12px;
}}
#{attr(root_id)} .ct-origin {{
  border: 1px solid var(--border, ThreeDShadow);
  border-radius: 4px;
  padding: 0 0.3rem;
}}
#{attr(root_id)} .ct-title {{
  font-weight: 500;
}}
#{attr(root_id)} .ct-excerpt {{
  margin: 0.2rem 0 0.15rem;
}}
#{attr(root_id)} .ct-children {{
  list-style: none;
  margin: 0.25rem 0 0.15rem;
  padding: 0 0 0 1rem;
  border-left: 1px solid var(--border, ThreeDShadow);
}}
#{attr(root_id)} .ct-children > li {{
  margin: 0.35rem 0 0;
}}
#{attr(root_id)} .ct-actions {{
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}}
#{attr(root_id)} .ct-action {{
  color: inherit;
  background: transparent;
  border: 1px solid var(--border, ThreeDShadow);
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}}
#{attr(root_id)} .ct-status-merged .ct-status {{
  color: var(--green, var(--foreground, CanvasText));
}}
#{attr(root_id)} .ct-status-discussing .ct-status,
#{attr(root_id)} .ct-status-forked .ct-status {{
  color: var(--blue, var(--foreground, CanvasText));
}}
#{attr(root_id)} .ct-note {{
  margin: 0.6rem 0 0;
  color: var(--muted-foreground, GrayText);
  font-size: 12px;
}}
</style>
{tree}
<p class="ct-note" data-ct-note hidden></p>
<script>
(() => {{
  const root = document.getElementById({json.dumps(root_id)});
  if (!root) return;
  const note = root.querySelector("[data-ct-note]");
  const send = async (prompt, title) => {{
    const api = window.openai;
    if (api && typeof api.sendFollowUpMessage === "function") {{
      await api.sendFollowUpMessage({{ prompt, title }});
      return;
    }}
    if (note) {{
      note.hidden = false;
      note.textContent = "在 Codex 对话里点击才会 fork / 打开 / 合并。";
    }}
  }};
  root.querySelectorAll(".ct-action").forEach((button) => {{
    button.addEventListener("click", () => {{
      send(button.getAttribute("data-prompt") || "", button.getAttribute("data-title") || "");
    }});
  }});
}})();
</script>
</div>
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a conversation tree HTML fragment.")
    parser.add_argument("--root-thread-id")
    parser.add_argument("--graph-file")
    parser.add_argument("--out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.graph_file:
        graph = json.loads(Path(args.graph_file).read_text(encoding="utf-8"))
        root_thread_id = str(graph.get("rootThreadId") or "graph")
    elif args.root_thread_id:
        graph = load_graph(args.root_thread_id)
        root_thread_id = args.root_thread_id
    else:
        json.dump({"ok": False, "error": "pass --root-thread-id or --graph-file"}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    fragment = render_fragment(graph)
    out = Path(args.out) if args.out else store_dir() / f"{graph_path(root_thread_id).stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(fragment, encoding="utf-8")
    json.dump({"ok": True, "path": str(out.resolve()), "rootThreadId": root_thread_id}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
