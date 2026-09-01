import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import readline from "node:readline";

const threadId = process.argv[2];
if (!threadId) throw new Error("Usage: node tests/mcp-smoke.mjs <thread-id>");

const child = spawn(process.execPath, ["server/index.mjs"], {
  cwd: new URL("..", import.meta.url),
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
});
const pending = new Map();
let nextId = 1;
let stderr = "";
child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => (stderr += chunk));
readline.createInterface({ input: child.stdout }).on("line", (line) => {
  const message = JSON.parse(line);
  const waiter = pending.get(String(message.id));
  if (!waiter) return;
  pending.delete(String(message.id));
  message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result);
});

function request(method, params = {}) {
  const id = String(nextId++);
  const promise = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out: ${method}\n${stderr}`)), 60_000);
    pending.set(id, {
      resolve: (value) => { clearTimeout(timeout); resolve(value); },
      reject: (error) => { clearTimeout(timeout); reject(error); },
    });
  });
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
  return promise;
}

try {
  const init = await request("initialize", { protocolVersion: "2025-06-18", clientInfo: { name: "smoke", version: "1" }, capabilities: {} });
  assert.equal(init.serverInfo.name, "conversation-tree");
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} })}\n`);
  const tools = await request("tools/list");
  assert.equal(tools.tools.length, 3);
  const resource = await request("resources/read", { uri: "ui://conversation-tree/canvas.html" });
  assert.match(resource.contents[0].mimeType, /mcp-app/);
  assert.match(resource.contents[0].text, /创建 Codex 原生分支/);
  assert.match(resource.contents[0].text, /返回主链路/);
  assert.match(resource.contents[0].text, /scheduleActiveRefresh/);
  assert.doesNotMatch(resource.contents[0].text, /在 Codex 打开/);
  const opened = await request("tools/call", { name: "conversation_tree_open", arguments: { threadId } });
  assert.equal(opened.structuredContent.tree.currentThreadId, threadId);
  assert.ok(opened.structuredContent.tree.lanes.length >= 1);
  assert.ok((opened.structuredContent.tree.explicitPointCount || 0) >= 0);
  const response = await fetch(opened.structuredContent.url);
  assert.equal(response.status, 200);
  assert.match(await response.text(), /Codex 会话树/);
  console.log(JSON.stringify({
    server: init.serverInfo,
    tools: tools.tools.map((tool) => tool.name),
    title: opened.structuredContent.tree.title,
    lanes: opened.structuredContent.tree.lanes.length,
    turns: opened.structuredContent.tree.lanes.reduce((sum, lane) => sum + lane.turns.length, 0),
    explicitPoints: opened.structuredContent.tree.explicitPointCount || 0,
    url: opened.structuredContent.url,
  }, null, 2));
} finally {
  child.kill();
}
