# Fork

Create one user-visible Codex task per requested point. The parent stays the index.

## Resolve

- Read selectors such as `1, 3, 5`, `第3点`, a quoted heading, a node id, or a tree click (`id: point-1-3`) against the graph, then against the latest completed assistant answer.
- Preserve the user's wording and per-point question.
- Ask only when a point cannot be identified. Do not add branches they did not request.

## Probe tools

Discover the exact native names in this session. Required:

- fork current task (`fork_thread`)
- rename child (`set_thread_title`)
- message child (`send_message_to_thread`)

If `fork_thread` is missing, stop and tell the user this needs Codex Desktop local thread tools. Never impersonate a fork with an internal subagent. `create_thread` is not a substitute: it does not inherit parent history.

## Sequence (once per requested point)

1. Ensure the graph exists (`graph.py init`) and the source answer is ingested (`ingest-points`).
2. If that assistant answer is still streaming, finish or stop it first. Forks copy completed history only.
3. Call `fork_thread` on the parent (the thread that contains the source answer). Same directory for discussion-only work.
4. Record the returned child thread id:

```bash
python scripts/graph.py fork --root-thread-id <parent> --point-id <id> --child-thread-id <child> --question "<optional user question>"
```

5. `set_thread_title` on the child to the script's `suggestedTitle` (topic · point). Keep it short.
6. `send_message_to_thread` on the child with `openingMessage` from the script. That message already includes the quoted point, the user's question when present, and an instruction to stay on this point.
7. Refresh the tree ([visualize.md](visualize.md)).
8. Offer `navigate_to_codex_page` / open-in-Codex when the user wants to switch into the child.

## Opening message contract

Do not replace the script output with a vague "please discuss this." The child must be able to continue without restating the entire parent answer.

## Finish

- Report each created child title and any failures.
- Do not duplicate a successful fork on retry.
- Do not merge unless the user asks.
