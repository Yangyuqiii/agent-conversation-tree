import fs from "node:fs/promises";
import path from "node:path";

async function readJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, "utf8"));
  } catch {
    return null;
  }
}

async function findInVisualizations(root, threadId, depth = 0) {
  if (depth > 9) return null;
  let entries;
  try {
    entries = await fs.readdir(root, { withFileTypes: true });
  } catch {
    return null;
  }
  const targetName = `${threadId}.json`;
  for (const entry of entries) {
    if (entry.isFile() && entry.name === targetName && path.basename(root) === "conversation-tree-data") {
      return path.join(root, entry.name);
    }
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const found = await findInVisualizations(path.join(root, entry.name), threadId, depth + 1);
    if (found) return found;
  }
  return null;
}

export async function loadExplicitGraph(threadId) {
  const profile = process.env.USERPROFILE || process.env.HOME;
  const codexHome = process.env.CODEX_HOME || (profile ? path.join(profile, ".codex") : null);
  const direct = [];
  if (process.env.CONVERSATION_TREE_DIR) direct.push(path.join(process.env.CONVERSATION_TREE_DIR, `${threadId}.json`));
  if (codexHome) direct.push(path.join(codexHome, "conversation-trees", `${threadId}.json`));
  for (const candidate of direct) {
    const graph = await readJson(candidate);
    if (graph) return { graph, file: candidate };
  }
  if (!codexHome) return null;
  const found = await findInVisualizations(path.join(codexHome, "visualizations"), threadId);
  if (!found) return null;
  const graph = await readJson(found);
  return graph ? { graph, file: found } : null;
}

function sourceTurnIndex(point) {
  const explicit = Number(point?.source?.turnIndex);
  if (Number.isInteger(explicit) && explicit > 0) return explicit - 1;
  const match = String(point?.source?.turnId || "").match(/turn-(\d+)/i);
  return match ? Math.max(0, Number(match[1]) - 1) : 0;
}

export function applyExplicitGraph(tree, loaded) {
  const graph = loaded?.graph;
  if (!graph || !Array.isArray(graph.nodes)) return tree;
  const rootLane = tree.lanes.find((lane) => lane.id === tree.rootThreadId) || tree.lanes[0];
  if (!rootLane) return tree;
  if (typeof graph.title === "string" && graph.title.trim()) tree.title = graph.title.trim();
  const points = graph.nodes.filter((node) => node?.kind === "point");
  for (const point of points) {
    const index = sourceTurnIndex(point);
    const turn = rootLane.turns[index] || rootLane.turns[0];
    if (!turn) continue;
    turn.explicitPoints ||= [];
    if (turn.explicitPoints.some((item) => item.id === point.id)) continue;
    turn.explicitPoints.push({
      id: point.id,
      title: point.title || "已确认要点",
      excerpt: point.excerpt || "",
      status: point.status || "open",
      childThreadId: point.codexThreadId || null,
      origin: point.source?.origin || "persisted",
    });
  }
  tree.annotationSource = loaded.file;
  tree.explicitPointCount = points.length;
  return tree;
}

