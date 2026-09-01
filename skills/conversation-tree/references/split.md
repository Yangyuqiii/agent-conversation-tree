# User-confirmed split

Use this when the assistant answer has **no** numbered list and **no** `##`/`###` headings, but the user wants to discuss it as 1, 2, 3.

Do not call `extract_points.py` on prose and pretend it found points. Do not ingest a split the user has not confirmed.

## When to use

- The user lists points themselves: `1 架构 2 数据 3 部署`, `分成三点：…`, or a numbered list in their message.
- The user asks to split without naming points: `帮我分成几点讨论`, `按 1、2、3 分开聊`.
- Visualization extracted nothing. Offer a split; do not write the graph yet.

Do **not** use this to replace extraction when the assistant answer already has numbered points or two-plus headings. Extract those.

## Confirm before write

Unconfirmed proposals exist only in chat. They must not enter the graph or the tree fragment.

1. Build a candidate list.
2. Echo it as a numbered list. Ask the user to confirm, edit, or cancel.
3. Ingest only after confirmation.
4. Render the tree. Fork/merge stay on [fork.md](fork.md) and [merge.md](merge.md).

### User-authored list

Parse the user's wording. Echo the parsed titles (and short excerpts). If a title is missing or two items collide, ask. After they say 确认 / 就这些 / 按这个 fork / OK, ingest.

### Agent-proposed list

If they asked to split but did not name the points, propose candidates from the answer. Wait for an explicit confirm or an edited list. Do not ingest on a vague `嗯` if the list is still ambiguous.

Confirmation examples: `确认`, `就这些`, `按这个写入`, `1 改成 缓存，2 3 不变`, `加上第4点：监控`.

Edits replace the candidate list. Echo the new list if the edit was not already a full numbered replacement, then ingest when it is clear.

## Candidate list

Prefer the user's titles. For excerpts, quote a short span from the **assistant** answer. Do not invent a new essay.

Show it like this before ingest:

```text
准备写入这三点，确认后才会进会话树：

1. 架构选型 — 模块化拆分
2. 数据模型 — 先定实体
3. 部署方案 — 分环境发布
```

If extraction was empty and they have not asked to split, ask once:

```text
这段回答没有编号要点。你可以指定 1、2、3，或让我提议一版，你确认后再写入树。
```

Do not propose and ingest in the same turn.

## Ingest

After confirmation, write JSON and ingest with origin `user-confirmed`:

```bash
python scripts/graph.py ingest-points \
  --root-thread-id <id> \
  --origin user-confirmed \
  --points-json <points.json>
```

JSON shape:

```json
{
  "points": [
    {"index": 1, "title": "架构选型", "excerpt": "模块化拆分"},
    {"index": 2, "title": "数据模型", "excerpt": "先定实体"},
    {"index": 3, "title": "部署方案", "excerpt": "分环境发布"}
  ]
}
```

Rules:

- `index` is a positive integer starting at 1.
- `title` is required and non-empty.
- `excerpt` should quote the source answer when possible.
- Never ingest an empty list to “create a tree”.

Then `render_tree.py` and emit the Visualize content reference.
