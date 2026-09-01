# Merge

Merge is an explicit write to the **parent** thread. Child turns never appear on the parent automatically.

## Choose a mode

If the user did not specify, ask once:

- `summary` — parent receives a short conclusion only
- `full` — parent receives the child transcript inside a collapsed `<details>` block
- `selective` — list candidate chunks (conclusions, decisions, code, todos); merge only the ones they pick

Do not invent a mode. Do not merge extra points.

## Build the body

- `summary`: read the child (`read_thread` when available, otherwise the current child transcript) and write a tight conclusion. No other points.
- `full`: the child user/assistant turns, oldest first. Skip tool noise unless the user asked for it.
- `selective`: number the candidates, wait for the user's list, then concatenate only those chunks.

## Record and send

```bash
python scripts/graph.py merge --root-thread-id <parent> --point-id <id> --mode <summary|full|selective> --body-file <payload.md> --source-thread-id <child>
```

The JSON field `mergeMessage` is the exact parent payload. It looks like:

```markdown
## Merged from: 数据模型 (point-1-2)
mode: summary
source_thread: thread_child
source_node: fork-point-1-2

<body>
```

`full` wraps `<body>` in `<details><summary>Full child transcript: ...</summary> ... </details>`.

Then:

- If this turn is already the parent, include `mergeMessage` as the user-visible parent update.
- If this turn is the child (or another task), `send_message_to_thread` to the parent with `mergeMessage`.
- Treat that block as accepted parent context from then on.
- Do not archive the child. The user may continue it and merge again.
- Refresh the tree. The point/fork status becomes `merged`.

## Failures

- Empty body: do not call `graph.py merge`.
- Missing parent thread id: ask; do not send the block to a guessed task.
- User said abandon: `graph.py abandon` only. There is no native stop-thread API; they stop the child in Codex themselves.
