---
name: conversation-tree
description: Visualizes a Codex session as a dsh-synapse-style interactive conversation canvas, marks follow-up points, creates native user-visible branches at completed turns, switches to child tasks, and merges selected child content back. Use when the user asks for a session tree, visual conversation graph, native branch, fork, split, open a branch, or merge a branch. Do not use for invisible subagent delegation.
---

# Conversation Tree

Open a real interactive canvas for the current Codex session. The MCP server reads Codex App Server history, groups tasks by their shared `sessionId`, and calls `thread/fork` for native branches. Keep the existing graph scripts only as compatibility storage for explicit point annotations and merge bookkeeping.

## Hard rules

- Never answer a visualization request with a `.canvas.tsx` source-file link, Mermaid text, or a static HTML file link.
- First call `conversation_tree_open` with the current Codex task/thread id.
- If the tool result is rendered inline as an MCP App, use that UI.
- If no inline UI is visible, take the returned loopback `url` and call `open_in_codex` with a Browser target and `placement: "right"`. This is the supported desktop fallback and must still appear as a visual panel, not source code.
- In the Browser fallback, **返回主链路** reloads the root task inside the same page. Do not navigate the Codex client merely to return to the root lane.
- Never use an internal/collaborator subagent as a conversation branch. A branch must be a user-visible Codex task.
- Create branches only after an explicit user click/request. Use `conversation_tree_fork`, or native `fork_thread` if the MCP server is unavailable.
- Preserve user-provided wording for graph and branch titles. Do not replace it with an invented research heading.
- `thread/fork` only accepts a completed `lastTurnId`. Report an in-progress turn clearly.
- Never merge unless the user asks. Keep child discussion out of the parent until merge.

## Visualize

1. Resolve the current Codex task/thread id from the app context.
2. Call `conversation_tree_open({ threadId })`.
3. When the host does not render the attached MCP App resource, open the returned `structuredContent.url` (or URL in text content) using `open_in_codex` as a Browser tab on the right.
4. Tell the user the panel is live: nodes open details, wheel zooms, blank-space drag pans, **从这里分支** invokes native `thread/fork`, and **返回主链路** reloads the root lane in the page.

When a fork starts an immediate prompt, the page polls the stored child turn until it reaches a terminal state. Treat `inProgress`, `completed`, `interrupted`, and `failed` distinctly; an empty answer is not sufficient evidence that work is still running.

The UI derives follow-up candidates from completed assistant messages. These are suggestions only; no branch is created until the user clicks or asks.

## Native fork and switch

- The visual **从这里分支** action calls `conversation_tree_fork` with the source `threadId`, selected `lastTurnId`, title, and optional follow-up prompt.
- The new task is created by Codex App Server and is visible in the normal sidebar.
- Returning to the root is a page-local tree reload in both embedded and Browser fallback modes.
- If the user separately asks to open a task in Codex, navigate to the exact returned child id with the native task tool.
- Do not retry a successful fork.

## User-confirmed point split

For unstructured prose, propose a numbered split in chat and wait for confirmation before persisting named points. Read [references/split.md](references/split.md). Use the compatibility scripts only when explicit annotation persistence is needed.

## Merge

Read [references/merge.md](references/merge.md). Ask for `summary`, `full`, or `selective` when the user did not choose. Send the merge payload to the parent task with native task tools, update compatibility graph storage when it exists, and refresh the visual tree. Do not archive the child.

## Compatibility scripts

Run from `skills/conversation-tree` when explicit point or merge records are needed:

```bash
python scripts/extract_points.py --text-file <message.txt>
python scripts/graph.py init --root-thread-id <id> --title "<user wording>"
python scripts/graph.py ingest-points --root-thread-id <id> --text-file <message.txt>
python scripts/graph.py fork --root-thread-id <id> --point-id <point-id> --child-thread-id <child-id>
python scripts/graph.py merge --root-thread-id <id> --point-id <point-id> --mode summary --body-file <payload.md>
```

See [references/graph.md](references/graph.md) for the compatibility schema.
