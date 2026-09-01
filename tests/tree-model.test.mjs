import assert from "node:assert/strict";
import test from "node:test";
import { applyExplicitGraph } from "../server/annotations.mjs";
import { buildConversationTree, deriveFollowups, turnText } from "../server/tree-model.mjs";

const turn = (id, user, agent) => ({
  id,
  status: "completed",
  items: [
    { id: `${id}-u`, type: "userMessage", content: [{ type: "text", text: user }] },
    { id: `${id}-a`, type: "agentMessage", text: agent },
  ],
});

test("turnText keeps user and assistant text", () => {
  assert.deepEqual(turnText(turn("t1", "用户原文", "回答原文")), { user: "用户原文", agent: "回答原文" });
});

test("deriveFollowups finds headings and numbered points without inventing content", () => {
  const points = deriveFollowups(turn("t1", "问题", "## 原生分支\n1. 右侧交互画布\n2. 保留用户原文"));
  assert.deepEqual(points, ["原生分支", "右侧交互画布", "保留用户原文"]);
});

test("buildConversationTree collapses copied fork history", () => {
  const shared = turn("t1", "最初问题", "最初回答");
  const root = {
    id: "root",
    sessionId: "session",
    name: "用户原文标题",
    preview: "最初问题",
    forkedFromId: null,
    createdAt: 1,
    updatedAt: 2,
    status: "idle",
    turns: [shared, turn("t2", "主线", "主线回答")],
  };
  const child = {
    id: "child",
    sessionId: "session",
    name: "右侧交互画布",
    preview: "最初问题",
    forkedFromId: "root",
    createdAt: 2,
    updatedAt: 3,
    status: "idle",
    turns: [shared, turn("t3", "分支问题", "分支回答")],
  };
  const tree = buildConversationTree("root", [root, child]);
  assert.equal(tree.title, "用户原文标题");
  assert.equal(tree.lanes.length, 2);
  assert.equal(tree.lanes[1].sharedTurnCount, 1);
  assert.equal(tree.lanes[1].turns[0].shared, true);
  assert.equal(tree.lanes[1].forkPointTurnId, "t1");
});

test("buildConversationTree keeps native fork ancestry when session ids differ", () => {
  const shared = turn("t1", "最初问题", "最初回答");
  const root = {
    id: "root",
    sessionId: "root-session",
    name: "主链路",
    preview: "最初问题",
    forkedFromId: null,
    createdAt: 1,
    updatedAt: 2,
    status: "idle",
    turns: [shared],
  };
  const child = {
    id: "child",
    sessionId: "child-session",
    name: "原生分支",
    preview: "分支问题",
    forkedFromId: "root",
    createdAt: 2,
    updatedAt: 3,
    status: "idle",
    turns: [shared, turn("t2", "分支问题", "分支回答")],
  };
  const tree = buildConversationTree("child", [root, child]);
  assert.equal(tree.rootThreadId, "root");
  assert.equal(tree.currentThreadId, "child");
  assert.deepEqual(tree.lanes.map((lane) => lane.id), ["root", "child"]);
  assert.equal(tree.lanes[1].forkPointTurnId, "t1");
});

test("applyExplicitGraph preserves user-confirmed point titles as canvas nodes", () => {
  const root = {
    id: "root", sessionId: "session", name: "app title", preview: "question", forkedFromId: null,
    createdAt: 1, updatedAt: 2, status: "idle", turns: [turn("t1", "问题", "回答")],
  };
  const tree = buildConversationTree("root", [root]);
  applyExplicitGraph(tree, { file: "graph.json", graph: { title: "用户原文", nodes: [
    { id: "point-1", kind: "point", title: "Reekin ChatTree", excerpt: "已确认", source: { turnIndex: 1, origin: "user-confirmed" } },
  ] } });
  assert.equal(tree.title, "用户原文");
  assert.equal(tree.explicitPointCount, 1);
  assert.equal(tree.lanes[0].turns[0].explicitPoints[0].title, "Reekin ChatTree");
});
