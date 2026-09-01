import crypto from "node:crypto";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { AppServerClient } from "./app-server-client.mjs";
import { applyExplicitGraph, loadExplicitGraph } from "./annotations.mjs";
import { buildConversationTree } from "./tree-model.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const UI_URI = "ui://conversation-tree/canvas.html";
const VERSION = "0.2.0";
const appServer = new AppServerClient();
let uiHtmlPromise;
let webServer;
let webAddress;
const webToken = crypto.randomBytes(24).toString("hex");

function uiHtml() {
  uiHtmlPromise ||= fs.readFile(path.join(here, "ui.html"), "utf8");
  return uiHtmlPromise;
}

function jsonResponse(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(body);
}

function validateThreadId(value, field = "threadId") {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${field} is required.`);
  return value.trim();
}

async function readTree(threadId) {
  const requestedId = validateThreadId(threadId);
  const current = await appServer.readThread(requestedId);
  const listed = await appServer.listThreads({ limit: 500, cwd: current.cwd || null });
  const uniqueListed = new Map(listed.map((thread) => [thread.id, thread]));
  const summaries = await Promise.all(
    [...uniqueListed.values()].map(async (thread) => {
      if (thread.id === current.id) return current;
      try {
        return await appServer.readThreadSummary(thread.id);
      } catch {
        return thread;
      }
    }),
  );
  const candidates = new Map([[current.id, current], ...summaries.map((thread) => [thread.id, thread])]);
  const relatedIds = new Set([current.id]);
  if (current.sessionId) {
    for (const thread of candidates.values()) {
      if (thread.sessionId === current.sessionId) relatedIds.add(thread.id);
    }
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (const thread of candidates.values()) {
      const parentId = thread.forkedFromId;
      if (!parentId) continue;
      if (relatedIds.has(thread.id) && candidates.has(parentId) && !relatedIds.has(parentId)) {
        relatedIds.add(parentId);
        changed = true;
      }
      if (relatedIds.has(parentId) && !relatedIds.has(thread.id)) {
        relatedIds.add(thread.id);
        changed = true;
      }
    }
  }

  const hydrated = [];
  for (const thread of candidates.values()) {
    if (!relatedIds.has(thread.id)) continue;
    if (thread.id === current.id && current.turns?.length) {
      hydrated.push(current);
      continue;
    }
    try {
      hydrated.push(await appServer.readThread(thread.id));
    } catch {
      hydrated.push(thread);
    }
  }
  const tree = buildConversationTree(requestedId, hydrated);
  const explicitGraph = await loadExplicitGraph(tree.rootThreadId);
  return applyExplicitGraph(tree, explicitGraph);
}

async function forkConversation(args) {
  const threadId = validateThreadId(args.threadId);
  const lastTurnId = args.lastTurnId ? validateThreadId(args.lastTurnId, "lastTurnId") : null;
  const source = await appServer.readThread(threadId);
  if (lastTurnId) {
    const turn = (source.turns || []).find((item) => item.id === lastTurnId);
    if (!turn) throw new Error("The selected turn does not belong to the source task.");
    const status = typeof turn.status === "string" ? turn.status : turn.status?.type;
    if (status === "inProgress") throw new Error("An in-progress turn cannot be forked.");
  }

  const child = await appServer.forkThread({ threadId, lastTurnId });
  const title = String(args.title || "").trim();
  if (title) await appServer.setThreadName(child.id, title);
  const prompt = String(args.prompt || "").trim();
  let turnStarted = false;
  let startedTurnId = null;
  if (prompt) {
    const started = await appServer.startTurn(child.id, prompt);
    startedTurnId = started?.turn?.id || null;
    turnStarted = true;
  }

  let tree;
  try {
    tree = await readTree(child.id);
  } catch {
    tree = null;
  }
  return {
    childThreadId: child.id,
    sourceThreadId: threadId,
    forkedAtTurnId: lastTurnId,
    title: title || child.name || child.preview || "未命名分支",
    turnStarted,
    startedTurnId,
    tree,
  };
}

async function startWebServer() {
  if (webAddress) return webAddress;
  const html = await uiHtml();
  webServer = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://127.0.0.1");
      if (url.searchParams.get("token") !== webToken) {
        jsonResponse(response, 403, { error: "Invalid conversation-tree token." });
        return;
      }
      if (request.method === "GET" && url.pathname === "/") {
        response.writeHead(200, {
          "content-type": "text/html; charset=utf-8",
          "content-length": Buffer.byteLength(html),
          "cache-control": "no-store",
          "content-security-policy": "default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:;",
          "x-content-type-options": "nosniff",
        });
        response.end(html);
        return;
      }
      if (request.method === "POST" && url.pathname === "/api/tool") {
        let raw = "";
        for await (const chunk of request) {
          raw += chunk;
          if (raw.length > 1_000_000) throw new Error("Request body is too large.");
        }
        const payload = JSON.parse(raw || "{}");
        const result = await callTool(payload.name, payload.arguments || {}, { includeContent: false });
        jsonResponse(response, 200, result.structuredContent || result);
        return;
      }
      jsonResponse(response, 404, { error: "Not found." });
    } catch (error) {
      jsonResponse(response, 500, { error: error.message || String(error) });
    }
  });
  await new Promise((resolve, reject) => {
    webServer.once("error", reject);
    webServer.listen(0, "127.0.0.1", resolve);
  });
  const address = webServer.address();
  webAddress = `http://127.0.0.1:${address.port}`;
  return webAddress;
}

const TOOLS = [
  {
    name: "conversation_tree_open",
    title: "打开交互式会话树",
    description: "读取一个 Codex task 的原生 session tree，并显示可缩放、可点击、可分支的会话画布。调用时传入当前 task/thread id。",
    inputSchema: {
      type: "object",
      properties: { threadId: { type: "string", description: "当前 Codex task/thread UUID" } },
      required: ["threadId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: {
      ui: { resourceUri: UI_URI },
      "openai/outputTemplate": UI_URI,
      "openai/toolInvocation/invoking": "正在构建会话树…",
      "openai/toolInvocation/invoked": "会话树已就绪",
    },
  },
  {
    name: "conversation_tree_read",
    title: "读取会话树数据",
    description: "读取 Codex App Server 的 thread/read 与 thread/list，并返回当前原生 session 的完整分支结构。",
    inputSchema: {
      type: "object",
      properties: { threadId: { type: "string" } },
      required: ["threadId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "conversation_tree_fork",
    title: "从指定轮次创建原生分支",
    description: "调用 Codex App Server thread/fork 在指定 lastTurnId 后创建侧栏可见的原生 task；可保留用户原文作为标题，并可选立即追问。",
    inputSchema: {
      type: "object",
      properties: {
        threadId: { type: "string", description: "源 Codex task/thread UUID" },
        lastTurnId: { type: "string", description: "分支包含到此 turn（可省略，表示完整 task）" },
        title: { type: "string", description: "分支标题，优先使用用户提供的原文" },
        prompt: { type: "string", description: "可选；在新分支中立即开始的追问" },
      },
      required: ["threadId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
];

async function callTool(name, args, { includeContent = true } = {}) {
  if (name === "conversation_tree_read") {
    const tree = await readTree(args.threadId);
    return {
      ...(includeContent ? { content: [{ type: "text", text: `已读取 ${tree.lanes.length} 个 Codex 原生任务分支。` }] } : {}),
      structuredContent: { tree },
    };
  }
  if (name === "conversation_tree_open") {
    const [tree, baseUrl] = await Promise.all([readTree(args.threadId), startWebServer()]);
    const url = `${baseUrl}/?token=${webToken}&threadId=${encodeURIComponent(args.threadId)}`;
    return {
      ...(includeContent
        ? {
            content: [
              { type: "text", text: `交互式会话树已就绪：${url}\n已读取 ${tree.lanes.length} 个原生任务分支。` },
            ],
          }
        : {}),
      structuredContent: { tree, url },
      _meta: { ui: { resourceUri: UI_URI } },
    };
  }
  if (name === "conversation_tree_fork") {
    const result = await forkConversation(args);
    return {
      ...(includeContent
        ? {
            content: [
              {
                type: "text",
                text: `已创建 Codex 原生分支 ${result.childThreadId}${result.turnStarted ? "，并已开始追问" : ""}。`,
              },
            ],
          }
        : {}),
      structuredContent: result,
    };
  }
  throw new Error(`Unknown tool: ${name}`);
}

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

async function handle(message) {
  if (message.method === "initialize") {
    return {
      protocolVersion: message.params?.protocolVersion || "2025-06-18",
      capabilities: { tools: { listChanged: false }, resources: { subscribe: false, listChanged: false } },
      serverInfo: { name: "conversation-tree", version: VERSION },
    };
  }
  if (message.method === "tools/list") return { tools: TOOLS };
  if (message.method === "resources/list") {
    return {
      resources: [
        { uri: UI_URI, name: "Codex 会话树画布", description: "Interactive native Codex session tree", mimeType: "text/html;profile=mcp-app" },
      ],
    };
  }
  if (message.method === "resources/read") {
    if (message.params?.uri !== UI_URI) throw Object.assign(new Error("Resource not found."), { code: -32002 });
    return { contents: [{ uri: UI_URI, mimeType: "text/html;profile=mcp-app", text: await uiHtml() }] };
  }
  if (message.method === "tools/call") return callTool(message.params?.name, message.params?.arguments || {});
  if (message.method === "ping") return {};
  throw Object.assign(new Error(`Method not found: ${message.method}`), { code: -32601 });
}

const input = readline.createInterface({ input: process.stdin });
input.on("line", async (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (message.id === undefined) return;
  try {
    send({ jsonrpc: "2.0", id: message.id, result: await handle(message) });
  } catch (error) {
    send({
      jsonrpc: "2.0",
      id: message.id,
      error: { code: error.code || -32000, message: error.message || String(error) },
    });
  }
});

async function shutdown() {
  appServer.close();
  if (webServer) await new Promise((resolve) => webServer.close(resolve));
  process.exit(0);
}
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
