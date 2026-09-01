# Visualize

Render the graph as a Codex inline visualization (HTML fragment). Do not deploy a Site. Do not `fetch` from the fragment.

## Render

```bash
python scripts/render_tree.py --root-thread-id <id>
```

Stdout JSON includes `path` (absolute). The file is an HTML **fragment**: no `<!doctype>`, `<html>`, `<head>`, or `<body>`. Default output is `~/.codex/conversation-trees/<rootThreadId>.html`.

Pass `--out <absolute-path>` when the thread has a dedicated visualization directory. Prefer a writable location outside the git checkout.

## Content reference

Whenever you create or update the fragment, include this on its own line in the same turn, using the absolute path from `render_tree.py`:

```text
visualize{"path":"<absolute-path>"}
```

Do not wrap it in a Markdown link. Do not announce it as a download. A short sentence about what the tree shows is enough.

Use `"mode":"wide"` only when the tree is unreadable at normal width, which should be rare.

## Click contract

Buttons call `window.openai.sendFollowUpMessage`. Treat those follow-ups as skill invocations:

- **Fork** — fork that point only
- **打开** — `navigate_to_codex_page` / open the bound child task
- **合并** — start merge; ask for `summary` / `full` / `selective` unless already specified

If Visualize is unavailable, show a compact Markdown tree (or Mermaid) plus the same fork/open/merge options, and still keep the graph file updated.

## Empty extraction

If `extract_points.py` returns nothing, do not invent nodes. Do not render a fake tree. Ask the user to specify 1, 2, 3, or to let you propose a split they confirm first. See [split.md](split.md). After a confirmed `--points-json` ingest, render as usual. User-confirmed points show a **用户指定** badge.

## What not to draw

Do not create a node per sentence. Only ingested points, their forks/merges, and turns needed as parents. Re-render after every successful fork or merge. Unconfirmed split proposals stay in chat and must not appear in the fragment.
