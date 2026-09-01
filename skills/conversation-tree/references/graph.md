# Graph schema

Each Codex thread is a flat list. This overlay stores parent/child structure, extracted points, forks, and merges.

Default location: `~/.codex/conversation-trees/<rootThreadId>.json`

Override with `CONVERSATION_TREE_DIR`. Files are UTF-8 JSON. `graph.py` writes them atomically.

## Document

```json
{
  "schemaVersion": 1,
  "rootThreadId": "thread_abc",
  "title": "Topic",
  "createdAt": "2026-08-31T15:00:00Z",
  "updatedAt": "2026-08-31T15:05:00Z",
  "nodes": []
}
```

One file per root thread. Nested forks stay in the same file.

## Node

| Field | Meaning |
| --- | --- |
| `id` | Stable id: `session`, `turn-N`, `point-<turn>-<index>`, `fork-<pointId>`, `merge-<pointId>-N` |
| `parentId` | Parent node id, or `null` on `session` |
| `kind` | `session` / `turn` / `point` / `fork` / `merge` |
| `title` | Short label |
| `excerpt` | First-line summary |
| `status` | `open` / `forked` / `discussing` / `merged` / `abandoned` |
| `codexThreadId` | Native Codex thread id; empty on virtual points until fork |
| `source` | Origin metadata (`messageId`, `pointIndex`, `heading`, `role`, `origin`) |
| `merge` | Present on merge nodes: `mode`, `at`, `sourceThreadId`, `excerpt`, `payload` |
| `createdAt` | UTC timestamp |

`point` is virtual until fork. `fork` holds the child thread id. `merge` records one write-back; a point may merge more than once.

`source.origin` on a point is `extracted` (numbered list / headings from the assistant answer) or `user-confirmed` (a 1-2-3 split the user approved). Do not write `user-confirmed` until confirmation; see [split.md](split.md).

## Commands

Run `python scripts/graph.py <command> --root-thread-id <id> ...`

- `init --title "..."` — create or reuse
- `ingest-points --text-file <file>` — parse numbered lists / `##` headings onto a turn (`origin=extracted`)
- `ingest-points --points-json <file> [--origin user-confirmed]` — insert a confirmed split; default origin is `user-confirmed` when `--points-json` is set. Each point needs `index` ≥ 1 and a non-empty `title`.
- `fork --point-id <id-or-3> --child-thread-id <id>` — bind native child thread; prints `openingMessage`
- `merge --point-id <id> --mode summary|full|selective --body-file <file>` — prints `mergeMessage`
- `abandon --point-id <id>` — mark point/fork abandoned; does not stop the Codex task
- `get` / `list` / `path` — inspect

`--point-id` accepts a node id, `3`, or `第3点`. If several turns share that index, the latest wins. If it is still ambiguous, ask the user.

## Isolation

Forked nodes keep talking on `codexThreadId`. Parent context does not include child turns until a merge payload is sent to the parent thread.
