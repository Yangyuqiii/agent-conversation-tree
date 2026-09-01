import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { TREE_SOURCE_KINDS } from "../server/app-server-client.mjs";

const ui = await readFile(new URL("../server/ui.html", import.meta.url), "utf8");

test("thread listing includes App Server-created user-visible forks", () => {
  assert.ok(TREE_SOURCE_KINDS.includes("appServer"));
  assert.ok(TREE_SOURCE_KINDS.includes("unknown"));
});

test("browser UI returns to the root without Codex navigation", () => {
  assert.match(ui, /id="root">[^<]*↩/);
  assert.match(ui, /id="return-root">返回主链路/);
  assert.match(ui, /async function returnToRoot\(\)/);
  assert.match(ui, /history\.replaceState/);
  assert.doesNotMatch(ui, /sendFollowUpMessage|navigator\.clipboard|在 Codex 打开/);
});

test("browser UI refreshes active turns and renders terminal states", () => {
  assert.match(ui, /scheduleActiveRefresh/);
  assert.match(ui, /setTimeout\(\(\)=>load\(threadId,\{fitView:false,quiet:true\}\),1500\)/);
  assert.match(ui, /正在生成回答…/);
  assert.match(ui, /回答已中断/);
  assert.match(ui, /回答失败/);
});
