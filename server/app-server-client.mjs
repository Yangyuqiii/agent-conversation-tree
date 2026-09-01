import { spawn } from "node:child_process";
import path from "node:path";
import readline from "node:readline";

const DEFAULT_TIMEOUT_MS = 30_000;
export const TREE_SOURCE_KINDS = Object.freeze([
  "cli",
  "vscode",
  "exec",
  "appServer",
  "subAgent",
  "subAgentReview",
  "subAgentCompact",
  "subAgentThreadSpawn",
  "subAgentOther",
  "unknown",
]);

export class AppServerClient {
  constructor({ command = process.env.CODEX_BIN, cwd = process.cwd() } = {}) {
    this.command = command || (process.platform === "win32" ? "codex.cmd" : "codex");
    this.cwd = cwd;
    this.child = null;
    this.pending = new Map();
    this.nextId = 1;
    this.stderr = "";
    this.ready = null;
  }

  async start() {
    if (this.ready) return this.ready;
    this.ready = this.#start();
    return this.ready;
  }

  async #start() {
    const childEnv = { ...process.env };
    if (process.platform === "win32") {
      const profile = childEnv.USERPROFILE || `${childEnv.HOMEDRIVE || ""}${childEnv.HOMEPATH || ""}`;
      if (profile) {
        childEnv.HOME ||= profile;
        childEnv.CODEX_HOME ||= path.join(profile, ".codex");
      }
    }
    this.child = spawn(this.command, ["app-server"], {
      cwd: this.cwd,
      env: childEnv,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      shell: process.platform === "win32",
    });

    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk) => {
      this.stderr = `${this.stderr}${chunk}`.slice(-8_000);
    });

    const lines = readline.createInterface({ input: this.child.stdout });
    lines.on("line", (line) => this.#onLine(line));
    this.child.once("error", (error) => this.#failAll(error));
    this.child.once("exit", (code, signal) => {
      this.#failAll(
        new Error(
          `Codex App Server exited (${signal || code || "unknown"}). ${this.stderr}`.trim(),
        ),
      );
      this.child = null;
      this.ready = null;
    });

    await this.request("initialize", {
      clientInfo: {
        name: "conversation-tree-plugin",
        title: "Conversation Tree",
        version: "0.2.0",
      },
      capabilities: { experimentalApi: true },
    });
    this.notify("initialized", {});
  }

  #onLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message;
    try {
      message = JSON.parse(trimmed);
    } catch {
      return;
    }

    if (message.id !== undefined && !message.method) {
      const pending = this.pending.get(String(message.id));
      if (!pending) return;
      this.pending.delete(String(message.id));
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new Error(message.error.message || JSON.stringify(message.error)));
      } else {
        pending.resolve(message.result);
      }
      return;
    }

    // The operations used by this plugin are read/fork/name operations and do not
    // require server-to-client approvals. Return a clear error if that ever changes.
    if (message.id !== undefined && message.method) {
      this.#write({
        id: message.id,
        error: { code: -32601, message: `Unsupported App Server request: ${message.method}` },
      });
    }
  }

  #failAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  #write(message) {
    if (!this.child?.stdin?.writable) {
      throw new Error("Codex App Server is not running.");
    }
    this.child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  async request(method, params = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    if (method !== "initialize") await this.start();
    const id = String(this.nextId++);
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Codex App Server request timed out: ${method}`));
      }, timeoutMs);
      timer.unref?.();
      this.pending.set(id, { resolve, reject, timer });
    });
    this.#write({ id, method, params });
    return promise;
  }

  notify(method, params = {}) {
    this.#write({ method, params });
  }

  async readThread(threadId) {
    const result = await this.request("thread/read", { threadId, includeTurns: true });
    return result.thread;
  }

  async readThreadSummary(threadId) {
    const result = await this.request("thread/read", { threadId, includeTurns: false });
    return result.thread;
  }

  async listThreads({ limit = 100, cwd = null } = {}) {
    const threads = [];
    let cursor = null;
    do {
      const params = {
        cursor,
        limit: Math.min(limit - threads.length, 100),
        archived: false,
        sourceKinds: TREE_SOURCE_KINDS,
        useStateDbOnly: false,
      };
      if (cwd) params.cwd = cwd;
      const result = await this.request("thread/list", params);
      threads.push(...(result.data || []));
      cursor = result.nextCursor || null;
    } while (cursor && threads.length < limit);
    return threads;
  }

  async forkThread({ threadId, lastTurnId = null }) {
    const params = { threadId, excludeTurns: false };
    if (lastTurnId) params.lastTurnId = lastTurnId;
    const result = await this.request("thread/fork", params, 60_000);
    return result.thread;
  }

  async setThreadName(threadId, name) {
    await this.request("thread/name/set", { threadId, name });
  }

  async startTurn(threadId, prompt) {
    return this.request(
      "turn/start",
      { threadId, input: [{ type: "text", text: prompt }] },
      60_000,
    );
  }

  close() {
    this.child?.kill();
    this.child = null;
    this.ready = null;
  }
}
