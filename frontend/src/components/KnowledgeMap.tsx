import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { api } from "../api/client";
import type { KnowledgeItem, KnowledgeStatus, Space } from "../api/types";
import {
  layoutWithElk,
  NODE_HEIGHT,
  NODE_WIDTH,
  RELATION_LABEL,
  STATUS_LABEL,
  type MapElements,
} from "../lib/graphLayout";
import { KnowledgeDetail } from "./KnowledgeDetail";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

type KnowledgeNodeData = {
  title: string;
  status: KnowledgeStatus;
  archived: boolean;
};

/** 自定义节点：标题 + 状态徽章；归档灰显虚线框。 */
function KnowledgeNode({ data }: NodeProps<Node<KnowledgeNodeData>>) {
  return (
    <div
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
      className={`flex flex-col justify-center gap-1 rounded-lg border bg-slate-900 px-3 py-2 ${
        data.archived
          ? "border-dashed border-slate-600 opacity-50"
          : "border-slate-600"
      }`}
    >
      <span className="truncate text-sm font-medium text-slate-100" title={data.title}>
        {data.title}
      </span>
      <span className="w-fit rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
        {STATUS_LABEL[data.status]}
      </span>
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 6, height: 6, background: "#64748b", border: "none" }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: "#64748b", border: "none" }}
      />
    </div>
  );
}

const nodeTypes = { knowledge: KnowledgeNode };

const LEGEND_RELATIONS = Object.entries(RELATION_LABEL) as [
  keyof typeof RELATION_LABEL,
  string,
][];

/**
 * M4 知识地图：React Flow 渲染 + ELK 自动布局。
 * 节点=知识条目、边=知识关系；点击节点打开治理详情；归档开关呈现合并闭环；
 * 切页签/刷新/治理变更后重取，保证与数据库实时一致。数据均来自真实 API。
 */
export function KnowledgeMap() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [elements, setElements] = useState<MapElements | null>(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<KnowledgeItem | null>(null);

  const loadGraph = useCallback(
    async (targetSpace: string, archived: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const graph = await api.getGraph({
          spaceId: targetSpace || null,
          includeArchived: archived,
        });
        setNodeCount(graph.nodes.length);
        setElements(await layoutWithElk(graph));
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void (async () => {
      try {
        setSpaces(await api.listSpaces());
      } catch (err) {
        setError(errorMessage(err));
      }
    })();
  }, []);

  useEffect(() => {
    setSelectedId(null);
    setSelectedItem(null);
    void loadGraph(spaceId, includeArchived);
  }, [spaceId, includeArchived, loadGraph]);

  async function openDetail(itemId: string) {
    setError(null);
    try {
      setSelectedItem(await api.getKnowledge(itemId));
      setSelectedId(itemId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const handleChanged = useCallback(async () => {
    await loadGraph(spaceId, includeArchived);
    if (selectedId) {
      try {
        setSelectedItem(await api.getKnowledge(selectedId));
      } catch {
        setSelectedId(null);
        setSelectedItem(null);
      }
    }
  }, [loadGraph, spaceId, includeArchived, selectedId]);

  const flowNodes = useMemo<Node<KnowledgeNodeData>[]>(
    () =>
      (elements?.nodes ?? []).map((n) => ({
        id: n.id,
        type: "knowledge",
        position: n.position,
        data: { title: n.title, status: n.status, archived: n.archived },
      })),
    [elements],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      (elements?.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        style: { stroke: e.color, strokeDasharray: e.dashed ? "6 3" : undefined },
        markerEnd: e.arrow ? { type: MarkerType.ArrowClosed, color: e.color } : undefined,
        labelStyle: { fill: "#cbd5e1", fontSize: 10 },
        labelBgStyle: { fill: "#0f172a" },
      })),
    [elements],
  );

  const inputClass =
    "rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
        <select
          value={spaceId}
          onChange={(e) => setSpaceId(e.target.value)}
          aria-label="地图空间"
          className={inputClass}
        >
          <option value="">全部空间</option>
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.kind === "personal" ? "（个人）" : ""}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            aria-label="显示归档"
            className="h-4 w-4 accent-slate-300"
          />
          显示归档
        </label>
        <button
          type="button"
          onClick={() => void loadGraph(spaceId, includeArchived)}
          disabled={loading}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          {loading ? "加载中…" : "刷新"}
        </button>
        <span className="ml-auto text-xs text-slate-500">
          节点 {nodeCount} · 边 {elements?.edges.length ?? 0}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-400">
        <span className="text-slate-500">图例：</span>
        {LEGEND_RELATIONS.map(([type, label]) => (
          <span key={type} className="flex items-center gap-1">
            <span
              className="inline-block h-0.5 w-4"
              style={{
                backgroundColor:
                  type === "duplicate_of" || type === "contradicts"
                    ? "#f87171"
                    : type === "depends_on"
                      ? "#60a5fa"
                      : type === "refines"
                        ? "#34d399"
                        : "#94a3b8",
              }}
            />
            {label}
            {type === "duplicate_of" ? "（虚线）" : ""}
          </span>
        ))}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-900 bg-red-950/50 p-3 text-sm text-red-300"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-md border border-emerald-900 bg-emerald-950/40 p-3 text-sm text-emerald-300"
        >
          {notice}
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="relative h-[480px] w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950 lg:w-auto lg:min-w-0 lg:flex-1">
          {loading ? (
            <p role="status" className="p-6 text-sm text-slate-400">
              正在加载知识地图…
            </p>
          ) : nodeCount === 0 ? (
            <p className="p-6 text-sm text-slate-500">
              当前空间暂无可展示的知识节点。可在「对话」提取或「知识库」新增知识，
              或开启「显示归档」查看已归档条目。
            </p>
          ) : (
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              onNodeClick={(_evt, node) => void openDetail(node.id)}
              fitView
              minZoom={0.2}
              maxZoom={2}
            >
              <Background color="#1e293b" gap={16} />
              <Controls />
            </ReactFlow>
          )}
        </div>

        {selectedId && selectedItem && (
          <aside className="w-full shrink-0 space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-4 lg:w-96">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">知识详情</h3>
              <button
                type="button"
                onClick={() => {
                  setSelectedId(null);
                  setSelectedItem(null);
                }}
                className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
              >
                关闭
              </button>
            </div>
            <KnowledgeDetail
              item={selectedItem}
              onNotice={setNotice}
              onError={setError}
              onChanged={() => void handleChanged()}
            />
          </aside>
        )}
      </div>
    </div>
  );
}