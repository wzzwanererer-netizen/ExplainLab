/**
 * Qoder Sites 纯静态在线体验模式（仅当显式设置 VITE_DEMO_MODE=true 构建静态演示站时启用）。
 * 本地桌面版、开发模式与全部自动化测试均直连真实后端，绝不加载此模块。
 */
import type {
  ConversationDetail,
  ExperimentSession,
  GraphResponse,
  HealthResponse,
  KnowledgeItem,
  KnowledgeRelation,
  KnowledgeVersion,
  ReviewRequest,
  SearchResponse,
  Space,
} from "./types";

const NOW = "2026-11-25T08:00:00Z";

const demoSpaces: Space[] = [
  {
    id: "sp-main",
    name: "个人总知识库",
    kind: "personal",
    description: "学习与科研核心知识主库",
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "sp-qoder",
    name: "Agent · Qoder",
    kind: "project",
    description: "由 Qoder 编程助手通过 MCP 自动沉淀的架构与工程副库",
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "sp-dsh",
    name: "Agent · DSH",
    kind: "project",
    description: "由 DSH 桌面助手通过 MCP 自动沉淀的科研调研副库",
    created_at: NOW,
    updated_at: NOW,
  },
];

let demoItems: KnowledgeItem[] = [
  {
    id: "k1",
    space_id: "sp-main",
    title: "RAG 混合检索与 RRF 融合排序",
    content:
      "## 核心原理\n结合 **全文检索（FTS5 / tsvector）** 与 **稠密语义向量检索**，通过倒数排名融合（RRF，`k=60`）平衡精确专有名词召回与跨表述语义召回。\n\n- 关联概念：[[知识图谱与语义关系治理]]、[[ExplainLab 分层解耦架构]]\n- 标签：#RAG #检索 #科研方法",
    status: "active",
    source_refs: [
      {
        id: "sr1",
        source_type: "conversation",
        uri: null,
        conversation_id: "conv-1",
        excerpt: "研究对话中对比了纯向量检索与混合 RRF 排序在中文术语查询中的表现",
        created_at: NOW,
      },
    ],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k2",
    space_id: "sp-main",
    title: "知识图谱与语义关系治理",
    content:
      "## 为什么知识库需要治理？\n普通笔记软件只管「存」，时间一长容易出现重复、过时与孤岛。ExplainLab 引入五类语义边：`related`、`depends_on`、`refines`、`duplicate_of`、`contradicts`，并对生效条目的变更设立 **审核门禁（HTTP 202）**。\n\n- 延伸阅读：[[间隔重复与主动学习实验]]\n- 标签：#知识图谱 #知识治理",
    status: "active",
    source_refs: [
      {
        id: "sr2",
        source_type: "manual",
        uri: null,
        conversation_id: null,
        excerpt: "整理自 ExplainLab M2 治理规范",
        created_at: NOW,
      },
    ],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k3",
    space_id: "sp-main",
    title: "间隔重复与主动学习实验",
    content:
      "## 从「被动收藏」到「主动掌握」\n基于已沉淀的知识条目，自动生成三类交互式学习实验：\n1. **测验（Quiz）**：服务端持有答案，作答后即时判分与解析；\n2. **概念对比（Compare）**：结构化拆解两条知识的异同；\n3. **学习路径（Chain）**：沿 `depends_on` 先修关系确定性编排。\n\n- 关联：[[知识图谱与语义关系治理]] #学习科学 #AI教育",
    status: "active",
    source_refs: [],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k4",
    space_id: "sp-qoder",
    title: "ExplainLab 分层解耦架构",
    content:
      "## 架构边界（由 Qoder 辅助工程化落地）\n严格遵循单向依赖：`frontend -> backend -> knowledge-core`。\n\n```text\nknowledge-core (纯 Python 领域核心，零 Web/ORM 依赖)\n       ▲ 经 Protocol 端口注入\nbackend (FastAPI + SQLAlchemy + SQLite/PostgreSQL 双适配)\n```\n\n- 全量自动化回归测试超过 **1520+** 项。\n- 关联：[[RAG 混合检索与 RRF 融合排序]] [[多 Agent MCP 共享外脑协议]] #架构 #Qoder",
    status: "active",
    source_refs: [
      {
        id: "sr4",
        source_type: "import",
        uri: "agent://Qoder",
        conversation_id: null,
        excerpt: "由 Qoder 通过 MCP 自动沉淀到专属副库",
        created_at: NOW,
      },
    ],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k5",
    space_id: "sp-qoder",
    title: "SQLite FTS5 与 PostgreSQL tsvector 双库适配",
    content:
      "## 方言隔离设计\n业务层与 `knowledge-core` 不写任何数据库方言 SQL；通过 `build_full_text_index` 按方言自动分派：\n- 本地桌面端默认 **SQLite + FTS5 trigram**（零部署开箱即用）；\n- 生产环境无缝切换 **PostgreSQL 原生 tsvector + GIN 索引**。\n\n- 关联：[[ExplainLab 分层解耦架构]] #数据库 #Qoder",
    status: "active",
    source_refs: [
      {
        id: "sr5",
        source_type: "import",
        uri: "agent://Qoder",
        conversation_id: null,
        excerpt: "由 Qoder 辅助实现双库迁移与真库验证",
        created_at: NOW,
      },
    ],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k6",
    space_id: "sp-dsh",
    title: "多 Agent MCP 共享外脑协议",
    content:
      "## 跨 Agent 知识打通\n通过标准 **MCP Server（JSON-RPC 2.0 over stdio）** 暴露 11 个知识读写与检索工具：\n- 支持 Qoder、Cursor、Claude、Codex、DSH、Trae、Kimi 等同时连接；\n- 每个外部 Agent 写入时自动按名称动态创建独立副库（如 `Agent · Qoder`、`Agent · DSH`），并在星图中既可独立查看，也可与主库联合展示。\n\n- 关联：[[ExplainLab 分层解耦架构]] #MCP #Agent",
    status: "active",
    source_refs: [
      {
        id: "sr6",
        source_type: "import",
        uri: "agent://DSH",
        conversation_id: null,
        excerpt: "由 DSH 桌面端通过 MCP 自动记录",
        created_at: NOW,
      },
    ],
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: "k7",
    space_id: "sp-main",
    title: "Obsidian 风格力导向知识星图",
    content:
      "## 零重依赖物理引擎\n纯 TypeScript 实现库仑斥力 + 胡克弹簧引力 + 矩形标签防重叠碰撞分离，配合 HiDPI Canvas 渲染：\n- 节点按连接度缩放半径；\n- 悬停自动聚光灯聚焦 1 跳邻居；\n- 支持主库与各 Agent 副库一键切换。\n\n- 关联：[[知识图谱与语义关系治理]] #可视化 #交互设计",
    status: "draft",
    source_refs: [],
    created_at: NOW,
    updated_at: NOW,
  },
];

const demoRelations: KnowledgeRelation[] = [
  { id: "r1", source_id: "k1", target_id: "k2", relation_type: "related", confidence: 0.92, origin: "llm", created_at: NOW },
  { id: "r2", source_id: "k3", target_id: "k2", relation_type: "depends_on", confidence: 0.95, origin: "manual", created_at: NOW },
  { id: "r3", source_id: "k4", target_id: "k1", relation_type: "refines", confidence: 0.9, origin: "manual", created_at: NOW },
  { id: "r4", source_id: "k5", target_id: "k4", relation_type: "depends_on", confidence: 0.96, origin: "manual", created_at: NOW },
  { id: "r5", source_id: "k6", target_id: "k4", relation_type: "refines", confidence: 0.93, origin: "manual", created_at: NOW },
  { id: "r6", source_id: "k7", target_id: "k2", relation_type: "refines", confidence: 0.91, origin: "manual", created_at: NOW },
];

let demoReviews: ReviewRequest[] = [
  {
    id: "rev-demo-1",
    item_id: "k1",
    action: "update_item",
    payload: { title: "RAG 混合检索与 RRF 融合排序（补充重排策略）" },
    reason: "外部 Agent 建议补充 Cross-Encoder 重排说明（生效条目受审核门禁保护）",
    status: "pending",
    created_at: NOW,
    resolved_at: null,
    resolution_note: null,
  },
];

const demoConversations: ConversationDetail[] = [
  {
    id: "conv-1",
    space_id: "sp-main",
    title: "如何构建不易腐化的个人科研知识库？",
    created_at: NOW,
    updated_at: NOW,
    messages: [
      {
        id: "m1",
        role: "user",
        content: "传统的笔记软件记多了就变成只进不出的坟墓，ExplainLab 是怎么解决的？",
        created_at: NOW,
      },
      {
        id: "m2",
        role: "assistant",
        content:
          "ExplainLab 通过三层闭环解决「知识腐化」问题：\n\n1. **混合检索 + 流式引用溯源**（参考《RAG 混合检索与 RRF 融合排序》）：提问时自动召回你自己的历史笔记作为上下文，并可一键溯源原条目。\n2. **审核门禁与语义星图**（参考《知识图谱与语义关系治理》）：AI 提取和外部 Agent 修改生效知识都会经过审核队列，避免污染主库。\n3. **交互式知识实验**（参考《间隔重复与主动学习实验》）：自动把笔记变成测验、概念对比和先修学习路径，把「存下来」变成「真正学会」。",
        created_at: NOW,
      },
    ],
  },
];

const demoExperiments: ExperimentSession[] = [
  {
    id: "exp-1",
    kind: "chain",
    title: "学习路径：间隔重复与主动学习实验",
    space_id: "sp-main",
    status: "active",
    item_ids: ["k2", "k3"],
    payload: {
      steps: [
        { item_id: "k2", title: "知识图谱与语义关系治理", relation_from_prev: null, position: 0 },
        { item_id: "k3", title: "间隔重复与主动学习实验", relation_from_prev: "depends_on", position: 1 },
      ],
    },
    created_at: NOW,
    updated_at: NOW,
  },
];

export const IS_STATIC_DEMO = import.meta.env.VITE_DEMO_MODE === "true";

function okJson(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

export async function handleDemoRequest(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const [cleanPath, qs = ""] = path.split("?");
  const params = new URLSearchParams(qs);
  const body =
    typeof init?.body === "string" && init.body.trim()
      ? (JSON.parse(init.body) as Record<string, unknown>)
      : {};

  if (cleanPath === "/api/health") {
    const health: HealthResponse = {
      status: "ok",
      app: "ExplainLab",
      version: "2.0.0-qoder-sites-demo",
      environment: "qoder-sites-preview",
      database: { connected: true, dialect: "sqlite (demo)", error: null },
      model_adapter: "demo-preview",
      embed_adapter: "configured",
      timestamp: new Date().toISOString(),
    };
    return okJson(health);
  }

  if (cleanPath === "/api/spaces" && method === "GET") {
    return okJson(demoSpaces);
  }
  if (cleanPath === "/api/spaces" && method === "POST") {
    const created: Space = {
      id: `sp-${Date.now()}`,
      name: String(body.name ?? "新空间"),
      kind: "project",
      description: (body.description as string | null) ?? null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    demoSpaces.push(created);
    return okJson(created, 201);
  }

  if (cleanPath === "/api/knowledge" && method === "GET") {
    const sid = params.get("space_id");
    const list = sid
      ? demoItems.filter((i) => i.space_id === sid)
      : demoItems;
    return okJson(list);
  }
  if (cleanPath === "/api/knowledge" && method === "POST") {
    const created: KnowledgeItem = {
      id: `k-${Date.now()}`,
      space_id: (body.space_id as string | null) ?? "sp-main",
      title: String(body.title ?? "未命名知识"),
      content: String(body.content ?? ""),
      status: "draft",
      source_refs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    demoItems = [created, ...demoItems];
    return okJson(created, 201);
  }

  const itemMatch = /^\/api\/knowledge\/([^/]+)$/.exec(cleanPath);
  if (itemMatch) {
    const id = itemMatch[1];
    const found = demoItems.find((i) => i.id === id);
    if (!found) return okJson({ detail: "条目不存在" }, 404);
    if (method === "GET") return okJson(found);
    if (method === "PATCH") {
      Object.assign(found, body, { updated_at: new Date().toISOString() });
      return okJson(found);
    }
    if (method === "DELETE") {
      demoItems = demoItems.filter((i) => i.id !== id);
      return new Response(null, { status: 204 });
    }
  }

  const subMatch = /^\/api\/knowledge\/([^/]+)\/(relations|versions|attachments|links|backlinks)$/.exec(
    cleanPath,
  );
  if (subMatch) {
    const [, id, sub] = subMatch;
    if (sub === "relations") {
      return okJson(demoRelations.filter((r) => r.source_id === id || r.target_id === id));
    }
    if (sub === "versions") {
      const found = demoItems.find((i) => i.id === id);
      const vers: KnowledgeVersion[] = found
        ? [
            {
              id: `v-${id}-1`,
              item_id: id,
              version: 1,
              title: found.title,
              content: found.content,
              change_summary: "初始快照",
              created_at: found.created_at,
            },
          ]
        : [];
      return okJson(vers);
    }
    return okJson([]);
  }

  if (cleanPath === "/api/graph") {
    const sid = params.get("space_id");
    const includeArchived = params.get("include_archived") === "true";
    const nodes = demoItems
      .filter((i) => (!sid || i.space_id === sid) && (includeArchived || i.status !== "archived"))
      .map((i) => ({ id: i.id, title: i.title, status: i.status, space_id: i.space_id }));
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = demoRelations
      .filter((r) => nodeIds.has(r.source_id) && nodeIds.has(r.target_id))
      .map((r) => ({
        id: r.id,
        source_id: r.source_id,
        target_id: r.target_id,
        relation_type: r.relation_type,
        confidence: r.confidence,
        origin: r.origin,
      }));
    const resp: GraphResponse = { nodes, edges };
    return okJson(resp);
  }

  if (cleanPath === "/api/search") {
    const q = (params.get("query") ?? "").trim().toLowerCase();
    const sid = params.get("space_id");
    const hits = demoItems
      .filter(
        (i) =>
          (!sid || i.space_id === sid) &&
          (!q || i.title.toLowerCase().includes(q) || i.content.toLowerCase().includes(q)),
      )
      .map((i) => ({
        item_id: i.id,
        score: 0.92,
        snippet: i.content.slice(0, 110),
        title: i.title,
        space_id: i.space_id,
        status: i.status,
        channels: { fts: 0.92 },
      }));
    const resp: SearchResponse = {
      query: q,
      mode: "hybrid",
      count: hits.length,
      embed_capability: "configured",
      results: hits,
    };
    return okJson(resp);
  }

  if (cleanPath === "/api/conversations" && method === "GET") {
    return okJson(demoConversations.map(({ messages: _m, ...rest }) => rest));
  }
  if (cleanPath === "/api/conversations" && method === "POST") {
    const created: ConversationDetail = {
      id: `conv-${Date.now()}`,
      space_id: (body.space_id as string | null) ?? "sp-main",
      title: String(body.title ?? "新研究对话"),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [],
    };
    demoConversations.unshift(created);
    return okJson(created, 201);
  }
  const convMatch = /^\/api\/conversations\/([^/]+)$/.exec(cleanPath);
  if (convMatch) {
    const found = demoConversations.find((c) => c.id === convMatch[1]);
    if (!found) return okJson({ detail: "会话不存在" }, 404);
    return okJson(found);
  }
  const chatMatch = /^\/api\/conversations\/([^/]+)\/chat$/.exec(cleanPath);
  if (chatMatch && method === "POST") {
    const conv = demoConversations.find((c) => c.id === chatMatch[1]);
    if (!conv) return okJson({ detail: "会话不存在" }, 404);
    const userContent = String(body.content ?? "");
    const now = new Date().toISOString();
    conv.messages.push({ id: `u-${Date.now()}`, role: "user", content: userContent, created_at: now });
    const reply = {
      id: `a-${Date.now() + 1}`,
      role: "assistant" as const,
      content: `（Qoder Sites 在线体验模式回复）已收到你的问题「${userContent}」。\n\n在本地原生桌面版中，ExplainLab 会直连你配置的真实大模型（如 DeepSeek），通过 SSE 逐字流式生成回答，并实时展示右侧知识库引用溯源抽屉。`,
      created_at: now,
    };
    conv.messages.push(reply);
    return okJson(reply);
  }

  if (cleanPath === "/api/reviews" && method === "GET") {
    const st = params.get("status");
    return okJson(st ? demoReviews.filter((r) => r.status === st) : demoReviews);
  }
  const revAction = /^\/api\/reviews\/([^/]+)\/(approve|reject)$/.exec(cleanPath);
  if (revAction && method === "POST") {
    const [, id, act] = revAction;
    const target = demoReviews.find((r) => r.id === id);
    if (!target) return okJson({ detail: "审核单不存在" }, 404);
    target.status = act === "approve" ? "approved" : "rejected";
    target.resolved_at = new Date().toISOString();
    target.resolution_note = (body.note as string | null) ?? null;
    return okJson(target);
  }

  if (cleanPath === "/api/experiments/sessions" && method === "GET") {
    return okJson(demoExperiments);
  }

  return okJson({ detail: `Demo 模式暂不支持此操作：${cleanPath}` }, 400);
}
