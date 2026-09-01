function compact(text, max = 180) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length <= max ? value : `${value.slice(0, max - 1).trimEnd()}…`;
}

function userInputText(content) {
  return (content || [])
    .map((item) => {
      if (typeof item === "string") return item;
      if (item?.type === "text" || item?.type === "input_text") return item.text || "";
      if (item?.text) return item.text;
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

export function turnText(turn) {
  const user = [];
  const agent = [];
  for (const item of turn.items || []) {
    if (item.type === "userMessage") user.push(userInputText(item.content));
    if (item.type === "agentMessage" && item.text) agent.push(item.text);
  }
  return {
    user: user.filter(Boolean).join("\n\n"),
    agent: agent.filter(Boolean).join("\n\n"),
  };
}

export function deriveFollowups(turn, limit = 5) {
  const { agent } = turnText(turn);
  if (!agent) return [];
  const candidates = [];
  const seen = new Set();
  for (const raw of agent.split(/\r?\n/)) {
    let line = raw.trim();
    line = line.replace(/^#{1,6}\s+/, "").replace(/^[-*+]\s+/, "").replace(/^\d+[.)、]\s+/, "");
    line = line.replace(/^\*\*(.+)\*\*[:：]?$/, "$1").trim();
    if (line.length < 4 || line.length > 120) continue;
    if (/^(https?:\/\/|```|[|>-])/.test(line)) continue;
    if (!/[\p{L}\p{N}]/u.test(line)) continue;
    const normalized = line.toLocaleLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    candidates.push(line);
    if (candidates.length >= limit) break;
  }
  return candidates;
}

function longestCommonTurnPrefix(parent, child) {
  const parentTurns = parent.turns || [];
  const childTurns = child.turns || [];
  let index = 0;
  while (index < parentTurns.length && index < childTurns.length) {
    const a = parentTurns[index];
    const b = childTurns[index];
    if (a.id === b.id) {
      index += 1;
      continue;
    }
    const at = turnText(a);
    const bt = turnText(b);
    if (at.user === bt.user && at.agent === bt.agent) {
      index += 1;
      continue;
    }
    break;
  }
  return index;
}

function relatedThreads(current, hydratedThreads) {
  const byId = new Map(hydratedThreads.map((thread) => [thread.id, thread]));
  const related = new Set([current.id]);
  if (current.sessionId) {
    for (const thread of hydratedThreads) {
      if (thread.sessionId === current.sessionId) related.add(thread.id);
    }
  }

  let changed = true;
  while (changed) {
    changed = false;
    for (const thread of hydratedThreads) {
      const parentId = thread.forkedFromId;
      if (!parentId) continue;
      if (related.has(thread.id) && byId.has(parentId) && !related.has(parentId)) {
        related.add(parentId);
        changed = true;
      }
      if (related.has(parentId) && !related.has(thread.id)) {
        related.add(thread.id);
        changed = true;
      }
    }
  }
  return hydratedThreads.filter((thread) => related.has(thread.id));
}

export function buildConversationTree(currentThreadId, hydratedThreads) {
  const byId = new Map(hydratedThreads.map((thread) => [thread.id, thread]));
  const current = byId.get(currentThreadId) || hydratedThreads[0];
  if (!current) throw new Error("No Codex task was found for this conversation tree.");

  const sessionThreads = relatedThreads(current, hydratedThreads);
  const sessionById = new Map(sessionThreads.map((thread) => [thread.id, thread]));
  const roots = sessionThreads.filter((thread) => !thread.forkedFromId || !sessionById.has(thread.forkedFromId));
  const root = roots.sort((a, b) => a.createdAt - b.createdAt)[0] || current;

  const lanes = sessionThreads
    .map((thread) => {
      const parent = thread.forkedFromId ? sessionById.get(thread.forkedFromId) : null;
      const sharedTurnCount = parent ? longestCommonTurnPrefix(parent, thread) : 0;
      const turns = (thread.turns || []).map((turn, index) => {
        const text = turnText(turn);
        return {
          id: turn.id,
          index,
          status: turn.status,
          startedAt: turn.startedAt,
          completedAt: turn.completedAt,
          user: compact(text.user, 240),
          agent: compact(text.agent, 320),
          userFull: text.user,
          agentFull: text.agent,
          followups: deriveFollowups(turn),
          shared: index < sharedTurnCount,
        };
      });
      return {
        id: thread.id,
        name: thread.name || compact(thread.preview, 80) || "未命名任务",
        preview: compact(thread.preview, 160),
        status: thread.status,
        current: thread.id === current.id,
        root: thread.id === root.id,
        forkedFromId: thread.forkedFromId || null,
        sharedTurnCount,
        forkPointTurnId: parent && sharedTurnCount > 0 ? parent.turns[sharedTurnCount - 1]?.id || null : null,
        createdAt: thread.createdAt,
        updatedAt: thread.updatedAt,
        turns,
      };
    })
    .sort((a, b) => a.createdAt - b.createdAt);

  return {
    sessionId: root.sessionId || current.sessionId || root.id,
    currentThreadId: current.id,
    rootThreadId: root.id,
    generatedAt: new Date().toISOString(),
    title: root.name || root.preview || "Codex 会话树",
    lanes,
  };
}
