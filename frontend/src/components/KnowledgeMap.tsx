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
import type {
  GraphResponse,
  KnowledgeItem,
  KnowledgeStatus,
  RelationType,
  Space,
} from "../api/types";
import {
  edgeVisual,
  layoutWithElk,
  NODE_HEIGHT,
  NODE_WIDTH,
  RELATION_LABEL,
  STATUS_LABEL,
  toMapElements,
  type MapElements,
} from "../lib/graphLayout";
import {
  DEFAULT_FORCE_CONFIG,
  getNeighborhood,
  type ForceConfig,
} from "../lib/obsidianForce";
import { KnowledgeDetail } from "./KnowledgeDetail";
import { ObsidianGraphCanvas } from "./ObsidianGraphCanvas";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

type KnowledgeNodeData = {
  title: string;
  status: KnowledgeStatus;
  archived: boolean;
};

type ViewMode = "obsidian" | "layered";
type LocalScope = "global" | "hop1" | "hop2";

/** 层级视图自定义节点（保留 ELK 架构图模式作为可选视图）。 */
function KnowledgeNode({ data }: NodeProps<Node<KnowledgeNodeData>>) {
  return (
    <div
      style={{
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        background: "var(--nesti-surface-1)",
        borderColor: "var(--nesti-border-strong)",
      }}
      className={`flex flex-col justify-center gap-1 rounded-lg border px-3 py-2 shadow-sm ${
        data.archived ? "border-dashed opacity-55" : ""
      }`}
    >
      <span
        className="truncate text-sm font-medium"
        style={{ color: "var(--nesti-text-primary)" }}
        title={data.title}
      >
        {data.title}
      </span>
      <span
        className="w-fit rounded-full px-2 py-0.5 text-xs"
        style={{
          background: "var(--nesti-surface-2)",
          color: "var(--nesti-text-secondary)",
        }}
      >
        {STATUS_LABEL[data.status]}
      </span>
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 6, height: 6, background: "var(--nesti-accent)", border: "none" }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: "var(--nesti-accent)", border: "none" }}
      />
    </div>
  );
}

const nodeTypes = { knowledge: KnowledgeNode };

const ALL_RELATIONS = Object.keys(RELATION_LABEL) as RelationType[];

const FALLBACK_SPACE_COLORS = [
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#f97316",
  "#6366f1",
];

function spaceColorFor(space: Space | undefined): string {
  if (!space) return "#3b74e8";
  if (space.kind === "personal") return "#3b74e8";
  const name = space.name.toLowerCase();
  if (name.includes("antigravity")) return "#0ea5e9";
  if (name.includes("codex")) return "#10b981";
  if (name.includes("dsh")) return "#f59e0b";
  if (name.includes("qoder")) return "#8b5cf6";
  if (name.includes("claude")) return "#f97316";
  if (name.includes("cursor")) return "#06b6d4";
  if (name.includes("trae")) return "#14b8a6";
  if (name.includes("pet") || name.includes("nesti")) return "#ec4899";
  if (name.includes("文件夹")) return "#64748b";
  let h = 0;
  for (let i = 0; i < space.id.length; i += 1) {
    h = (h * 31 + space.id.charCodeAt(i)) >>> 0;
  }
  return FALLBACK_SPACE_COLORS[h % FALLBACK_SPACE_COLORS.length];
}

interface KnowledgeMapProps {
  onLocateInKnowledge?: (spaceId: string | null | undefined, itemId: string) => void;
}

/**
 * 知识地图：默认 Obsidian 风格力导向星图（支持悬停聚光灯、物理拖拽、局部 1/2 跳图谱、
 * 关系筛选、物理参数调节），并保留 ELK 层级视图切换；点击节点打开右侧治理详情。
 */
export function KnowledgeMap({ onLocateInKnowledge }: KnowledgeMapProps = {}) {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [rawGraph, setRawGraph] = useState<GraphResponse | null>(null);
  const [layeredElements, setLayeredElements] = useState<MapElements | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<KnowledgeItem | null>(null);

  // Obsidian 图谱专属交互状态
  const [viewMode, setViewMode] = useState<ViewMode>("obsidian");
  const [searchQuery, setSearchQuery] = useState("");
  const [localScope, setLocalScope] = useState<LocalScope>("global");
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [enabledRelations, setEnabledRelations] = useState<Record<RelationType, boolean>>({
    related: true,
    depends_on: true,
    refines: true,
    duplicate_of: true,
    contradicts: true,
  });
  const [forceConfig, setForceConfig] = useState<ForceConfig>(DEFAULT_FORCE_CONFIG);
  const [showArrows, setShowArrows] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [reheatToken, setReheatToken] = useState(0);

  const loadGraph = useCallback(async (targetSpace: string, archived: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const graph = await api.getGraph({
        spaceId: targetSpace || null,
        includeArchived: archived,
      });
      setRawGraph(graph);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

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
    setLocalScope("global");
    void loadGraph(spaceId, includeArchived);
  }, [spaceId, includeArchived, loadGraph]);

  // 根据关系筛选 + 局部图谱作用域计算当前可见子图
  const { visibleGraph, elements, edgeTypes } = useMemo(() => {
    if (!rawGraph) {
      return {
        visibleGraph: null as GraphResponse | null,
        elements: { nodes: [], edges: [] } as MapElements,
        edgeTypes: new Map<string, RelationType>(),
      };
    }

    const filteredEdges = rawGraph.edges.filter(
      (e) => enabledRelations[e.relation_type],
    );

    let finalNodes = rawGraph.nodes;
    let finalEdges = filteredEdges;

    if (localScope !== "global" && selectedId) {
      const hops: 1 | 2 = localScope === "hop1" ? 1 : 2;
      const hood = getNeighborhood(
        filteredEdges.map((e) => ({
          id: e.id,
          source: e.source_id,
          target: e.target_id,
        })),
        selectedId,
        hops,
      );
      finalNodes = rawGraph.nodes.filter((n) => hood.nodeIds.has(n.id));
      finalEdges = filteredEdges.filter((e) => hood.edgeIds.has(e.id));
    }

    const subGraph: GraphResponse = { nodes: finalNodes, edges: finalEdges };
    const mapEls = toMapElements(subGraph);
    const typeMap = new Map<string, RelationType>(
      finalEdges.map((e) => [e.id, e.relation_type]),
    );
    return { visibleGraph: subGraph, elements: mapEls, edgeTypes: typeMap };
  }, [rawGraph, enabledRelations, localScope, selectedId]);

  // 仅当切换到“层级视图”时计算 ELK 坐标
  useEffect(() => {
    if (viewMode !== "layered" || !visibleGraph) return;
    let cancelled = false;
    void layoutWithElk(visibleGraph).then((res) => {
      if (!cancelled) setLayeredElements(res);
    });
    return () => {
      cancelled = true;
    };
  }, [viewMode, visibleGraph]);

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
        setLocalScope("global");
      }
    }
  }, [loadGraph, spaceId, includeArchived, selectedId]);

  const flowNodes = useMemo<Node<KnowledgeNodeData>[]>(
    () =>
      (layeredElements?.nodes ?? []).map((n) => ({
        id: n.id,
        type: "knowledge",
        position: n.position,
        data: { title: n.title, status: n.status, archived: n.archived },
      })),
    [layeredElements],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      (layeredElements?.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        style: { stroke: e.color, strokeDasharray: e.dashed ? "6 3" : undefined },
        markerEnd: e.arrow ? { type: MarkerType.ArrowClosed, color: e.color } : undefined,
        labelStyle: { fill: "var(--nesti-text-secondary)", fontSize: 10 },
        labelBgStyle: { fill: "var(--nesti-surface-1)" },
      })),
    [layeredElements],
  );

  const toggleRelation = (type: RelationType) => {
    setEnabledRelations((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const spaceById = useMemo(
    () => new Map(spaces.map((s) => [s.id, s])),
    [spaces],
  );

  const nodeColors = useMemo(() => {
    const map = new Map<string, string>();
    if (!rawGraph) return map;
    for (const n of rawGraph.nodes) {
      const sp = n.space_id ? spaceById.get(n.space_id) : undefined;
      map.set(n.id, spaceColorFor(sp));
    }
    return map;
  }, [rawGraph, spaceById]);

  const activeSpaceLegend = useMemo(() => {
    if (!rawGraph) return [];
    const counts = new Map<string, number>();
    for (const n of rawGraph.nodes) {
      const key = n.space_id ?? "__personal__";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([key, count]) => {
        const sp =
          key === "__personal__"
            ? spaces.find((s) => s.kind === "personal")
            : spaceById.get(key);
        return {
          key,
          label: sp ? sp.name.replace(/^Agent\s*·\s*/i, "") : "个人总知识库",
          color: spaceColorFor(sp),
          count,
        };
      })
      .sort((a, b) => b.count - a.count);
  }, [rawGraph, spaces, spaceById]);

  const totalNodes = elements.nodes.length;
  const totalEdges = elements.edges.length;

  return (
    <div className="flex h-full flex-col gap-3">
      {/* 顶部工具栏（Nesti Fluent 风格） */}
      <div
        className="flex flex-wrap items-center gap-2.5 rounded-xl border px-3.5 py-2.5 shadow-xs"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
        }}
      >
        <select
          value={spaceId}
          onChange={(e) => setSpaceId(e.target.value)}
          aria-label="地图空间"
          className="rounded-lg border px-2.5 py-1.5 text-sm outline-none"
          style={{
            background: "var(--nesti-surface-0)",
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-primary)",
          }}
        >
          <option value="">全部空间</option>
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.kind === "personal" ? "（个人）" : ""}
            </option>
          ))}
        </select>

        <input
          type="search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="高亮搜索节点…"
          aria-label="搜索图谱节点"
          className="w-44 rounded-lg border px-2.5 py-1.5 text-sm outline-none sm:w-56"
          style={{
            background: "var(--nesti-surface-0)",
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-primary)",
          }}
        />

        <label
          className="flex cursor-pointer items-center gap-1.5 text-sm"
          style={{ color: "var(--nesti-text-secondary)" }}
        >
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            aria-label="显示归档"
            className="h-4 w-4 rounded accent-[var(--nesti-accent)]"
          />
          显示归档
        </label>

        {/* 星图 / 层级 视图切换 */}
        <div
          className="inline-flex rounded-lg border p-0.5 text-xs"
          style={{
            background: "var(--nesti-surface-0)",
            borderColor: "var(--nesti-border-subtle)",
          }}
        >
          <button
            type="button"
            onClick={() => setViewMode("obsidian")}
            className="rounded-md px-2.5 py-1 font-medium transition-colors"
            style={
              viewMode === "obsidian"
                ? { background: "var(--nesti-accent)", color: "#ffffff" }
                : { color: "var(--nesti-text-secondary)" }
            }
          >
            星图模式
          </button>
          <button
            type="button"
            onClick={() => setViewMode("layered")}
            className="rounded-md px-2.5 py-1 font-medium transition-colors"
            style={
              viewMode === "layered"
                ? { background: "var(--nesti-accent)", color: "#ffffff" }
                : { color: "var(--nesti-text-secondary)" }
            }
          >
            层级视图
          </button>
        </div>

        <button
          type="button"
          onClick={() => void loadGraph(spaceId, includeArchived)}
          disabled={loading}
          className="rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-40"
          style={{
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-secondary)",
          }}
        >
          {loading ? "加载中…" : "刷新"}
        </button>

        <span
          className="ml-auto rounded-full px-2.5 py-0.5 text-xs tabular-nums"
          style={{
            background: "var(--nesti-surface-2)",
            color: "var(--nesti-text-secondary)",
          }}
        >
          节点 {totalNodes} · 边 {totalEdges}
        </span>
      </div>

      {/* 主库 + 动态 Agent 副库快捷切换条 */}
      {spaces.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-0.5 text-xs">
          <button
            type="button"
            onClick={() => setSpaceId("")}
            className="rounded-full border px-3 py-1 font-medium transition-colors"
            style={
              spaceId === ""
                ? {
                    background: "var(--nesti-accent)",
                    borderColor: "var(--nesti-accent)",
                    color: "#ffffff",
                  }
                : {
                    background: "var(--nesti-surface-1)",
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-text-secondary)",
                  }
            }
          >
            全部星图（主库 + 副库）
          </button>
          {spaces.map((s) => {
            const active = spaceId === s.id;
            const isAgent = s.name.startsWith("Agent ·");
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setSpaceId(s.id)}
                className="rounded-full border px-3 py-1 font-medium transition-colors"
                style={
                  active
                    ? {
                        background: "var(--nesti-accent)",
                        borderColor: "var(--nesti-accent)",
                        color: "#ffffff",
                      }
                    : {
                        background: "var(--nesti-surface-1)",
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nesti-text-secondary)",
                      }
                }
              >
                {s.kind === "personal"
                  ? `${s.name}（主库）`
                  : isAgent
                    ? `${s.name}（副库）`
                    : s.name}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-600 dark:text-emerald-400"
        >
          {notice}
        </div>
      )}

      {/* 主画布 + 右侧详情检查器 */}
      <div className="flex min-h-[560px] flex-1 flex-col gap-3 lg:flex-row">
        <div
          className="relative min-h-[560px] flex-1 overflow-hidden rounded-xl border shadow-xs"
          style={{
            background: "var(--nesti-surface-0)",
            borderColor: "var(--nesti-border-subtle)",
          }}
        >
          {loading ? (
            <p
              role="status"
              className="p-6 text-sm"
              style={{ color: "var(--nesti-text-secondary)" }}
            >
              正在加载知识地图…
            </p>
          ) : totalNodes === 0 ? (
            <p
              className="p-6 text-sm"
              style={{ color: "var(--nesti-text-secondary)" }}
            >
              当前空间暂无可展示的知识节点。可在「对话」提取或「知识库」新增知识，
              或开启「显示归档」查看已归档条目。
            </p>
          ) : viewMode === "obsidian" ? (
            <ObsidianGraphCanvas
              elements={elements}
              edgeTypes={edgeTypes}
              nodeColors={nodeColors}
              selectedId={selectedId}
              searchQuery={searchQuery}
              config={forceConfig}
              showArrows={showArrows}
              showEdgeLabels={showEdgeLabels}
              reheatToken={reheatToken}
              onSelectNode={(id) => void openDetail(id)}
              onDoubleClickNode={(id) => {
                void openDetail(id);
              }}
            />
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
              <Background color="var(--nesti-border-subtle)" gap={18} />
              <Controls />
            </ReactFlow>
          )}

          {/* Obsidian 风格右上角浮动图谱设置面板 */}
          {!loading && totalNodes > 0 && (
            <div className="absolute right-3 top-3 z-10 flex flex-col items-end">
              <button
                type="button"
                onClick={() => setSettingsOpen((v) => !v)}
                className="rounded-lg border px-2.5 py-1 text-xs font-medium shadow-sm backdrop-blur-md transition-colors hover:bg-[var(--nesti-surface-hover)]"
                style={{
                  background: "var(--nesti-surface-1)",
                  borderColor: "var(--nesti-border-subtle)",
                  color: "var(--nesti-text-primary)",
                }}
              >
                {settingsOpen ? "收起图谱面板" : "图谱设置"}
              </button>

              {settingsOpen && (
                <div
                  className="mt-2 w-64 space-y-3 rounded-xl border p-3 text-xs shadow-lg backdrop-blur-md"
                  style={{
                    background: "var(--nesti-surface-1)",
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  {/* 局部图谱切换 */}
                  <div className="space-y-1.5">
                    <div
                      className="flex items-center justify-between font-semibold"
                      style={{ color: "var(--nesti-text-primary)" }}
                    >
                      <span>视野范围</span>
                      {!selectedId && (
                        <span className="text-[10px] font-normal opacity-70">
                          点击节点启用局部
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-3 gap-1">
                      {(
                        [
                          ["global", "全局"],
                          ["hop1", "1 跳"],
                          ["hop2", "2 跳"],
                        ] as const
                      ).map(([scope, label]) => {
                        const disabled = scope !== "global" && !selectedId;
                        const active = localScope === scope;
                        return (
                          <button
                            key={scope}
                            type="button"
                            disabled={disabled}
                            onClick={() => setLocalScope(scope)}
                            className="rounded-md border px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-40"
                            style={
                              active
                                ? {
                                    background: "var(--nesti-accent)",
                                    borderColor: "var(--nesti-accent)",
                                    color: "#ffffff",
                                  }
                                : {
                                    background: "var(--nesti-surface-0)",
                                    borderColor: "var(--nesti-border-subtle)",
                                    color: "var(--nesti-text-secondary)",
                                  }
                            }
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* 空间 / Agent 配色图例 */}
                  {activeSpaceLegend.length > 0 && (
                    <div
                      className="space-y-1.5 border-t pt-2.5"
                      style={{ borderColor: "var(--nesti-border-subtle)" }}
                    >
                      <div
                        className="font-semibold"
                        style={{ color: "var(--nesti-text-primary)" }}
                      >
                        空间 / Agent 配色
                      </div>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                        {activeSpaceLegend.slice(0, 8).map((entry) => (
                          <div
                            key={entry.key}
                            className="flex items-center gap-1.5 truncate text-[11px]"
                            title={`${entry.label}（${entry.count} 条）`}
                          >
                            <span
                              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                              style={{ background: entry.color }}
                            />
                            <span className="truncate">{entry.label}</span>
                            <span className="ml-auto font-mono text-[10px] opacity-65">
                              {entry.count}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 关系筛选 & 图例 */}
                  <div className="space-y-1.5 border-t pt-2.5" style={{ borderColor: "var(--nesti-border-subtle)" }}>
                    <div
                      className="font-semibold"
                      style={{ color: "var(--nesti-text-primary)" }}
                    >
                      关系筛选与图例
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {ALL_RELATIONS.map((type) => {
                        const visual = edgeVisual(type);
                        return (
                          <label
                            key={type}
                            className="flex cursor-pointer items-center gap-1.5"
                          >
                            <input
                              type="checkbox"
                              checked={enabledRelations[type]}
                              onChange={() => toggleRelation(type)}
                              className="h-3.5 w-3.5 accent-[var(--nesti-accent)]"
                            />
                            <span
                              className="inline-block h-0.5 w-3 shrink-0"
                              style={{
                                backgroundColor: visual.color,
                                borderTop: visual.dashed
                                  ? `2px dashed ${visual.color}`
                                  : undefined,
                              }}
                            />
                            <span className="truncate">{RELATION_LABEL[type]}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>

                  {/* 星图物理参数与显示选项 */}
                  {viewMode === "obsidian" && (
                    <div
                      className="space-y-2 border-t pt-2.5"
                      style={{ borderColor: "var(--nesti-border-subtle)" }}
                    >
                      <div className="flex items-center justify-between">
                        <span
                          className="font-semibold"
                          style={{ color: "var(--nesti-text-primary)" }}
                        >
                          星图力学与显示
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setForceConfig(DEFAULT_FORCE_CONFIG);
                            setReheatToken((t) => t + 1);
                          }}
                          className="text-[11px] hover:underline"
                          style={{ color: "var(--nesti-accent)" }}
                        >
                          重置并散开
                        </button>
                      </div>

                      <label className="block space-y-0.5">
                        <div className="flex justify-between text-[11px]">
                          <span>节点大小</span>
                          <span className="tabular-nums">
                            {forceConfig.nodeScale.toFixed(1)}x
                          </span>
                        </div>
                        <input
                          type="range"
                          min={0.6}
                          max={1.8}
                          step={0.1}
                          value={forceConfig.nodeScale}
                          onChange={(e) =>
                            setForceConfig((c) => ({
                              ...c,
                              nodeScale: Number(e.target.value),
                            }))
                          }
                          className="w-full accent-[var(--nesti-accent)]"
                        />
                      </label>

                      <label className="block space-y-0.5">
                        <div className="flex justify-between text-[11px]">
                          <span>节点斥力</span>
                          <span className="tabular-nums">
                            {Math.round(forceConfig.repulsion)}
                          </span>
                        </div>
                        <input
                          type="range"
                          min={2000}
                          max={15000}
                          step={400}
                          value={forceConfig.repulsion}
                          onChange={(e) =>
                            setForceConfig((c) => ({
                              ...c,
                              repulsion: Number(e.target.value),
                            }))
                          }
                          className="w-full accent-[var(--nesti-accent)]"
                        />
                      </label>

                      <label className="block space-y-0.5">
                        <div className="flex justify-between text-[11px]">
                          <span>连线距离</span>
                          <span className="tabular-nums">
                            {Math.round(forceConfig.linkDistance)}px
                          </span>
                        </div>
                        <input
                          type="range"
                          min={90}
                          max={340}
                          step={10}
                          value={forceConfig.linkDistance}
                          onChange={(e) =>
                            setForceConfig((c) => ({
                              ...c,
                              linkDistance: Number(e.target.value),
                            }))
                          }
                          className="w-full accent-[var(--nesti-accent)]"
                        />
                      </label>

                      <div className="flex items-center justify-between pt-1">
                        <label className="flex cursor-pointer items-center gap-1.5">
                          <input
                            type="checkbox"
                            checked={showArrows}
                            onChange={(e) => setShowArrows(e.target.checked)}
                            className="h-3.5 w-3.5 accent-[var(--nesti-accent)]"
                          />
                          <span>方向箭头</span>
                        </label>
                        <label className="flex cursor-pointer items-center gap-1.5">
                          <input
                            type="checkbox"
                            checked={showEdgeLabels}
                            onChange={(e) => setShowEdgeLabels(e.target.checked)}
                            className="h-3.5 w-3.5 accent-[var(--nesti-accent)]"
                          />
                          <span>常显边标签</span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 右侧知识详情检查器 */}
        {selectedId && selectedItem && (
          <aside
            className="w-full shrink-0 space-y-3 overflow-y-auto rounded-xl border p-4 shadow-xs lg:w-96"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
            }}
          >
            <div className="flex items-center justify-between gap-2">
              <h3
                className="text-sm font-semibold"
                style={{ color: "var(--nesti-text-primary)" }}
              >
                知识详情
              </h3>
              <div className="flex items-center gap-1.5">
                {onLocateInKnowledge && (
                  <button
                    type="button"
                    onClick={() =>
                      onLocateInKnowledge(selectedItem.space_id, selectedItem.id)
                    }
                    className="rounded-md px-2.5 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90"
                    style={{ background: "var(--nesti-accent)" }}
                  >
                    定位到知识库 →
                  </button>
                )}
                <button
                  type="button"
                  onClick={() =>
                    setLocalScope((prev) => (prev === "global" ? "hop1" : "global"))
                  }
                  className="rounded-md border px-2 py-1 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    borderColor: "var(--nesti-border-subtle)",
                    color:
                      localScope !== "global"
                        ? "var(--nesti-accent)"
                        : "var(--nesti-text-secondary)",
                  }}
                >
                  {localScope === "global" ? "局部图谱" : "返回全局"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(null);
                    setSelectedItem(null);
                    setLocalScope("global");
                  }}
                  className="rounded-md border px-2 py-1 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  关闭
                </button>
              </div>
            </div>
            <KnowledgeDetail
              item={selectedItem}
              onNotice={setNotice}
              onError={setError}
              onChanged={() => void handleChanged()}
              onNavigateItem={(targetId) => void openDetail(targetId)}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
