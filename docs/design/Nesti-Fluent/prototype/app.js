/* ==========================================================================
   ExplainLab · Nesti Fluent Interactive Desktop Prototype
   Demonstrates:
   - Nesti Workspace Shell (Titlebar, Brand Slot, Global Search, Primary Rail,
     Secondary Module Nav, Multi-Tab Bar, Main Workspace, Collapsible Inspector, Status Bar)
   - 7 Distinct Business Views grounded in real ExplainLab V2 backend APIs:
     01 Dashboard | 02 Chat | 03 Knowledge | 04 Search | 05 Knowledge Map | 06 Experiments | 07 Reviews
   - Theme Studio (Light/Dark/System, 6 Presets, Custom Accent, Density, Radius, Shadow, JSON Export/Import)
   - Component States Matrix (10 states across Buttons, Inputs, Menus, Tables, Dialogs, Side Panels)
   ========================================================================== */

const ICONS = {
  dashboard: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="3.5" rx="1"/><rect x="9" y="7.5" width="5" height="6.5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/></svg>',
  chat: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 3.5h11a1 1 0 0 1 1 1v6.5a1 1 0 0 1-1 1H6l-3 2.5V12h-.5a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"/></svg>',
  knowledge: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2.5h7.5L13 5v8.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z"/><path d="M10 2.5V5.5h3"/><path d="M5 8h6M5 10.5h4.5"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="7.2" cy="7.2" r="4.7"/><path d="m10.8 10.8 3 3"/></svg>',
  map: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="3.5" cy="4" r="1.8"/><circle cx="12.5" cy="4" r="1.8"/><circle cx="8" cy="12" r="1.8"/><path d="M5.2 4.6 10.8 4.6M4.4 5.6 7.1 10.4M11.6 5.6 8.9 10.4"/></svg>',
  experiments: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2.5h4M6.8 2.5v3.8L3.2 12.2A1.2 1.2 0 0 0 4.2 14h7.6a1.2 1.2 0 0 0 1-1.8L9.2 6.3V2.5"/><path d="M5 10.5h6"/></svg>',
  reviews: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h10v10H3z" rx="1.5"/><path d="m5.5 8.2 1.7 1.8 3.5-3.8"/></svg>',
  palette: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2a6 6 0 1 0 0 12h.8a1.4 1.4 0 0 0 1.4-1.4c0-.5-.3-.9-.5-1.2-.2-.3-.1-.8.4-.9A4 4 0 0 0 14 8a6 6 0 0 0-6-6Z"/><circle cx="5.2" cy="7.2" r=".7" fill="currentColor"/><circle cx="7.4" cy="5.1" r=".7" fill="currentColor"/><circle cx="10.4" cy="5.8" r=".7" fill="currentColor"/></svg>',
  layers: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 6 3.2L8 8.4 2 5.2 8 2Z"/><path d="m2 8.2 6 3.2 6-3.2"/><path d="m2 11.2 6 3.2 6-3.2"/></svg>',
  bell: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4.2 6.5a3.8 3.8 0 1 1 7.6 0c0 3.2 1.2 4.3 1.2 4.3H3s1.2-1.1 1.2-4.3Z"/><path d="M6.6 13a1.5 1.5 0 0 0 2.8 0"/></svg>',
  panelRight: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M10.2 2.5v11"/></svg>',
  panelLeft: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M5.8 2.5v11"/></svg>',
  sun: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="2.8"/><path d="M8 1.8v1.4M8 12.8v1.4M1.8 8h1.4M12.8 8h1.4M3.6 3.6l1 1M11.4 11.4l1 1M12.4 3.6l-1 1M4.6 11.4l-1 1"/></svg>',
  moon: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12.8 10.2A5.3 5.3 0 0 1 5.8 3.2a5.5 5.5 0 1 0 7 7Z"/></svg>',
  folder: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4.2A1.2 1.2 0 0 1 3.2 3h3l1.3 1.5h5.3A1.2 1.2 0 0 1 14 5.7v6.1A1.2 1.2 0 0 1 12.8 13H3.2A1.2 1.2 0 0 1 2 11.8V4.2Z"/></svg>',
  paperclip: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m11.8 5.2-5.3 5.3a1.8 1.8 0 0 1-2.5-2.5l5.7-5.7a3 3 0 0 1 4.2 4.2l-5.7 5.7a4.2 4.2 0 0 1-6-6l5.1-5.1"/></svg>',
  link: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6.8 9.2a2.8 2.8 0 0 0 4 0l2-2a2.8 2.8 0 0 0-4-4L7.7 4.3"/><path d="M9.2 6.8a2.8 2.8 0 0 0-4 0l-2 2a2.8 2.8 0 1 0 4 4l1.1-1.1"/></svg>',
  upload: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10.5V3M5 5.8 8 2.8l3 3"/><path d="M2.5 11.5v1.3A1.2 1.2 0 0 0 3.7 14h8.6a1.2 1.2 0 0 0 1.2-1.2v-1.3"/></svg>',
  download: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v7.5M5 7.7 8 10.7l3-3"/><path d="M2.5 11.5v1.3A1.2 1.2 0 0 0 3.7 14h8.6a1.2 1.2 0 0 0 1.2-1.2v-1.3"/></svg>',
  hub: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="2" width="12" height="12" rx="2.5"/><path d="M5.5 8h5M8 5.5v5"/></svg>',
  agent: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 13a5 5 0 0 1 10 0"/></svg>',
  user: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="5.5" r="2.6"/><path d="M3.2 13.5a4.8 4.8 0 0 1 9.6 0"/></svg>',
  close: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
  plus: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 3v10M3 8h10"/></svg>',
  refresh: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 8a5.5 5.5 0 1 1-1.4-3.7"/><path d="M13.5 2.8v2.7h-2.7"/></svg>',
};

const PRESETS = [
  { id: "glacier", name: "Glacier Blue", desc: "默认冰蓝钴蓝", primary: "#2463EB", secondary: "#79CAFF" },
  { id: "iris", name: "Iris Purple", desc: "鸢尾蓝紫", primary: "#6D5CE7", secondary: "#A79BFF" },
  { id: "emerald", name: "Emerald Green", desc: "翡翠青绿", primary: "#0F9D75", secondary: "#6EE7B7" },
  { id: "amber", name: "Amber Orange", desc: "琥珀暖橙", primary: "#D97706", secondary: "#FCD34D" },
  { id: "graphite", name: "Graphite", desc: "石墨中性", primary: "#475569", secondary: "#94A3B8" },
  { id: "sakura", name: "Sakura Pink", desc: "樱粉柔调", primary: "#DB4B7D", secondary: "#F9A8D4" },
];

const DATA = {
  spaces: [
    { id: "sp-personal", name: "个人总知识库", kind: "personal", count: 4 },
    { id: "sp-v2", name: "ExplainLab V2 架构", kind: "project", count: 3 },
  ],
  knowledge: [
    {
      id: "k-101",
      spaceId: "sp-v2",
      title: "StorageKeyLock 双方言锁契约",
      status: "active",
      tags: ["batch-b", "postgresql", "lock"],
      updated: "12:15",
      attachments: [
        { id: "att-1", filename: "lock-sequence.pdf", mime: "application/pdf", size: "184 KB", hash: "17a4d4a0...780570f" },
        { id: "att-2", filename: "advisory-diagram.png", mime: "image/png", size: "62 KB", hash: "8289305c...7a90eab" },
      ],
      links: [{ target: "GC 七态状态机与隔离槽", resolution: "resolved" }],
      backlinks: [{ source: "Active ZIP 导入审核流程" }],
      versions: [
        { v: 3, summary: "补齐 PG advisory PID 串行化说明", at: "2026-11-25 12:15" },
        { v: 2, summary: "区分 SQLite 租约与 PG 互斥边界", at: "2026-11-24 19:20" },
      ],
      content: "PostgreSQL 路径下 StorageKeyLock 的权威来自会话级 Advisory Lock，storage_lock 表行仅保存单调 fencing token 与展示租约；行 TTL 过期不授权接管仍存活的 Advisory Lock。\n\n参见 [[GC 七态状态机与隔离槽]]。",
    },
    {
      id: "k-102",
      spaceId: "sp-v2",
      title: "GC 七态状态机与隔离槽",
      status: "active",
      tags: ["gc", "orp", "recovery"],
      updated: "11:42",
      attachments: [
        { id: "att-3", filename: "gc-states.md", mime: "text/markdown", size: "4.2 KB", hash: "b6c3e453...585c3b3" },
      ],
      links: [],
      backlinks: [{ source: "StorageKeyLock 双方言锁契约" }],
      versions: [{ v: 1, summary: "初始快照", at: "2026-11-24 15:10" }],
      content: "最后一条引用删除时入队 pending 任务；Worker 持锁复核 COUNT(attachment)==0 后将正式文件原子移动至 _quarantine/<key>.<task_id>，等待 24 小时后安全 purge。",
    },
    {
      id: "k-103",
      spaceId: "sp-v2",
      title: "Active ZIP 导入审核流程",
      status: "draft",
      tags: ["import", "staging", "review"],
      updated: "10:50",
      attachments: [],
      links: [{ target: "StorageKeyLock 双方言锁契约", resolution: "resolved" }],
      backlinks: [],
      versions: [{ v: 1, summary: "草稿创建", at: "2026-11-25 10:50" }],
      content: "Active 条目含正文或附件变更的 ZIP 导入不直接落库，而是写入带摘要校验的 __a1_import envelope 与 staging 目录，待审批通过后在业务事务提交前发布正式 blob。",
    },
    {
      id: "k-104",
      spaceId: "sp-personal",
      title: "PostgreSQL 原生 tsvector 混合检索",
      status: "active",
      tags: ["retrieval", "fts", "rrf"],
      updated: "昨天",
      attachments: [],
      links: [],
      backlinks: [],
      versions: [{ v: 2, summary: "补充 CJK ILIKE 回退说明", at: "2026-11-23 21:00" }],
      content: "PostgreSQL 使用原生 tsvector/tsquery + GIN 索引与 RRF(k=60) 融合排序；simple 分词对无空格中文不成词时回退 JOIN knowledge_fts 的 ILIKE 匹配。",
    },
    {
      id: "k-105",
      spaceId: "sp-personal",
      title: "旧版单表全文索引草稿（已归档）",
      status: "archived",
      tags: ["legacy"],
      updated: "11-18",
      attachments: [],
      links: [],
      backlinks: [],
      versions: [{ v: 1, summary: "合并归档", at: "2026-11-18 14:30" }],
      content: "已通过重复合并归档并建立 duplicate_of 关系，指向 PostgreSQL 原生 tsvector 混合检索。",
    },
  ],
  conversations: [
    {
      id: "c-1",
      title: "PG Advisory Lock 与行 TTL 边界讨论",
      space: "ExplainLab V2 架构",
      updated: "12:10",
      messages: [
        { role: "user", time: "12:08", text: "在 PostgreSQL 下，如果 storage_lock 表的 lease_expires_at 过期了，但原连接的会话 advisory lock 还活着，新 Worker 能接管吗？" },
        {
          role: "assistant",
          time: "12:09",
          text: "不能接管。按冻结契约 D-B02：\n1. PostgreSQL 路径以会话级 Advisory Lock 为唯一互斥权威。\n2. storage_lock 行仅保存单调递增的 fencing token 与展示租约。\n3. 只有原客户端连接关闭或进程崩溃后，PostgreSQL 自动释放 Advisory Lock，新 Worker 才能成功 acquire 并使 token 严格 +1。",
          sources: ["StorageKeyLock 双方言锁契约", "GC 七态状态机与隔离槽"],
        },
      ],
    },
    {
      id: "c-2",
      title: "Nesti Fluent 桌面工作区信息架构",
      space: "个人总知识库",
      updated: "11:20",
      messages: [
        { role: "user", time: "11:18", text: "ExplainLab 未来嵌入 Nesti 时，Shell 和业务模块应该如何划分边界？" },
        {
          role: "assistant",
          time: "11:19",
          text: "主应用标题栏、左侧 Nesti 主导航 Rail、全局命令搜索与 ThemeProvider 属于 Nesti Workspace Shell；ExplainLab 作为功能模块提供次级导航、7 个业务视图与可折叠右侧检查器，通过 props 接收 apiBaseUrl 与受控主题令牌。",
          sources: ["Active ZIP 导入审核流程"],
        },
      ],
    },
  ],
  reviews: [
    {
      id: "rev-01",
      action: "update_item",
      isZipImport: true,
      itemTitle: "StorageKeyLock 双方言锁契约",
      itemId: "k-101",
      status: "pending",
      createdAt: "2026-11-25 12:12",
      reason: "Active ZIP 导入：新增 PG 18.6 双 Worker 并发证据与序列图附件",
      stagingId: "9f4b2c1a-8e21-4d7c-9a10-33b8c9d0e1f2",
      contextDigest: "e3b0c44298fc1c14...95991b7852b855",
      stagedAttachments: [
        { ordinal: "000001.bin", filename: "pg-advisory-trace.pdf", mime: "application/pdf", size: "212 KB", sha256: "9b3a5dc1...8126a75f" },
        { ordinal: "000002.bin", filename: "lock-matrix.png", mime: "image/png", size: "94 KB", sha256: "489edacd...6696bc2c" },
      ],
      diffOld: "- 行 TTL 过期后由后台扫描清理锁记录。",
      diffNew: "+ 行 TTL 过期不授权接管仍存活的 Advisory Lock；仅当原 PG backend 连接断开后释放。",
    },
    {
      id: "rev-02",
      action: "merge_duplicate",
      isZipImport: false,
      itemTitle: "旧版单表全文索引草稿（已归档）",
      itemId: "k-105",
      status: "approved",
      createdAt: "2026-11-24 18:40",
      reason: "查重分析判定与「PostgreSQL 原生 tsvector 混合检索」置信度 98% 重复",
      resolutionNote: "合并来源并保留 duplicate_of 关系",
      diffOld: "状态: active",
      diffNew: "状态: archived · 关系: duplicate_of → k-104",
    },
  ],
  experiments: [
    {
      id: "exp-1",
      kind: "quiz",
      title: "StorageKeyLock 与 GC 隔离期测验",
      status: "active",
      itemCount: 2,
      createdAt: "11-25 12:00",
      questions: [
        {
          index: 0,
          kind: "single_choice",
          prompt: "PostgreSQL 模式下，若 storage_lock 表的 lease_expires_at 已过期，但原会话 Advisory Lock 仍存活，新 Worker 尝试 acquire 会发生什么？",
          options: [
            "直接覆写行记录并强制接管锁",
            "无法获取 Advisory Lock，acquire 失败且不得执行物理删除",
            "自动触发 pg_terminate_backend 杀死旧连接",
            "降级为 SQLite 租约逻辑",
          ],
          correct: 1,
          explanation: "按冻结契约 D-B02，PG 会话级 Advisory Lock 是唯一互斥权威，行 TTL 过期绝不授权接管。",
          sourceTitle: "StorageKeyLock 双方言锁契约",
        },
        {
          index: 1,
          kind: "true_false",
          prompt: "GC Worker 在 24 小时隔离等待期内，任务状态应保持为 running（租约过期 + next_retry_at=+24h），而不是 pending。",
          options: ["正确", "错误"],
          correct: 0,
          explanation: "GC-04/05 规定 quarantine 后维持 running 状态，通过 next_retry_at 保护 24h 安全期不被提前认领。",
          sourceTitle: "GC 七态状态机与隔离槽",
        },
      ],
    },
    {
      id: "exp-2",
      kind: "compare",
      title: "SQLite 租约 vs PostgreSQL Advisory Lock 对比",
      status: "completed",
      itemCount: 2,
      createdAt: "11-24 20:15",
      compare: {
        a: "StorageKeyLock 双方言锁契约",
        b: "GC 七态状态机与隔离槽",
        relationType: "depends_on",
        relationship: "GC 状态机的所有隔离与清除物理动作均依赖 StorageKeyLock 提供互斥与 fencing 保护。",
        similarities: ["均采用单调递增的 fencing token 防止旧 Worker 误写", "均在物理文件系统操作前二次校验租约状态"],
        differences: ["StorageKeyLock 聚焦跨操作互斥原语", "GC 状态机管理 7 态流转、退避重试与 24h 隔离等待期"],
      },
    },
    {
      id: "exp-3",
      kind: "chain",
      title: "Active ZIP 导入审核学习路径",
      status: "completed",
      itemCount: 3,
      createdAt: "11-24 16:30",
      steps: [
        { pos: 1, title: "GC 七态状态机与隔离槽", rel: null, goal: false },
        { pos: 2, title: "StorageKeyLock 双方言锁契约", rel: "依赖上一步", goal: false },
        { pos: 3, title: "Active ZIP 导入审核流程", rel: "依赖上一步", goal: true },
      ],
    },
  ],
};

const state = {
  page: "dashboard", // dashboard | chat | knowledge | search | map | experiments | reviews | theme-studio | components
  themeMode: "light", // light | dark | system
  preset: "glacier",
  customAccent: "#2463eb",
  density: "comfortable",
  radius: "balanced",
  shadow: "subtle",
  subnavOpen: true,
  inspectorOpen: true,
  commandOpen: false,
  selectedKnowledgeId: "k-101",
  knowledgeInspectorTab: "preview", // preview | attachments | links | governance
  selectedConversationId: "c-1",
  selectedReviewId: "rev-01",
  reviewFilter: "all",
  searchQuery: "Advisory Lock",
  searchMode: "hybrid",
  selectedSearchId: "k-101",
  mapIncludeArchived: true,
  selectedMapNodeId: "k-101",
  selectedExperimentId: "exp-1",
  quizPicked: { 0: 1 },
  themeStudioTab: "studio", // studio | components
  toast: null,
};

function applyThemeTokens() {
  const root = document.documentElement;
  const effectiveTheme =
    state.themeMode === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : state.themeMode;
  root.setAttribute("data-theme", effectiveTheme);
  root.setAttribute("data-preset", state.preset);
  root.setAttribute("data-density", state.density);
  root.setAttribute("data-radius", state.radius);
  root.setAttribute("data-shadow", state.shadow);
  if (state.preset === "custom") {
    root.style.setProperty("--nf-accent", state.customAccent);
    root.style.setProperty("--nf-accent-hover", state.customAccent);
    root.style.setProperty("--nf-module-icon", state.customAccent);
    root.style.setProperty("--nf-accent-soft", state.customAccent + "1f");
    root.style.setProperty("--nf-accent-border", state.customAccent + "55");
  } else {
    ["--nf-accent", "--nf-accent-hover", "--nf-module-icon", "--nf-accent-soft", "--nf-accent-border"].forEach((k) =>
      root.style.removeProperty(k)
    );
  }
}

function statusPill(status) {
  if (status === "active") return '<span class="nf-pill success">生效</span>';
  if (status === "draft") return '<span class="nf-pill accent">草稿</span>';
  if (status === "archived") return '<span class="nf-pill">已归档</span>';
  if (status === "pending") return '<span class="nf-pill warning">待审核</span>';
  if (status === "approved") return '<span class="nf-pill success">已批准</span>';
  if (status === "rejected") return '<span class="nf-pill danger">已驳回</span>';
  return `<span class="nf-pill">${status}</span>`;
}

const NAV_PAGES = [
  { id: "dashboard", label: "工作台", icon: "dashboard" },
  { id: "chat", label: "研究对话", icon: "chat", count: "2" },
  { id: "knowledge", label: "知识库", icon: "knowledge", count: "5" },
  { id: "search", label: "混合检索", icon: "search" },
  { id: "map", label: "知识地图", icon: "map" },
  { id: "experiments", label: "知识实验", icon: "experiments", count: "3" },
  { id: "reviews", label: "审核队列", icon: "reviews", count: "1" },
];

function renderDashboard() {
  const pendingReviews = DATA.reviews.filter((r) => r.status === "pending");
  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">工作台</span>
      <span class="nf-pill">个人总知识库 · ExplainLab V2 架构</span>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="nf-btn" data-goto="chat">${ICONS.chat} 新建研究对话</button>
        <button class="nf-btn" data-goto="knowledge">${ICONS.upload} 导入 Markdown / ZIP</button>
        <button class="nf-btn nf-btn-primary" data-goto="knowledge">${ICONS.plus} 新建知识</button>
      </div>
    </div>
    <div class="nf-scroll" style="flex:1;overflow-y:auto;padding:16px;display:grid;grid-template-columns:1.35fr 1fr;gap:14px;align-content:start;">
      <div style="display:flex;flex-direction:column;gap:14px;">
        <section class="nf-pane">
          <div class="nf-section-head">
            <span>最近知识</span>
            <button class="nf-btn" style="height:24px;font-size:11.5px;" data-goto="knowledge">全部 5 条</button>
          </div>
          <table class="nf-table">
            <thead><tr><th>标题</th><th>状态</th><th>附件</th><th>更新</th></tr></thead>
            <tbody>
              ${DATA.knowledge.slice(0, 4).map((k) => `
                <tr data-open-knowledge="${k.id}">
                  <td style="font-weight:500;">${k.title}</td>
                  <td>${statusPill(k.status)}</td>
                  <td class="nf-muted nf-mono">${k.attachments.length}</td>
                  <td class="nf-muted">${k.updated}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </section>

        <section class="nf-pane">
          <div class="nf-section-head">
            <span>最近研究对话</span>
            <button class="nf-btn" style="height:24px;font-size:11.5px;" data-goto="chat">进入对话</button>
          </div>
          <div style="padding:6px 0;">
            ${DATA.conversations.map((c) => `
              <div data-open-conv="${c.id}" style="padding:9px 12px;border-bottom:1px solid var(--nf-border-subtle);cursor:pointer;display:flex;justify-content:space-between;align-items:center;">
                <div>
                  <div style="font-weight:500;">${c.title}</div>
                  <div class="nf-muted" style="font-size:11.5px;margin-top:2px;">${c.space} · ${c.messages.length} 条消息</div>
                </div>
                <span class="nf-muted" style="font-size:11.5px;">${c.updated}</span>
              </div>
            `).join("")}
          </div>
        </section>
      </div>

      <div style="display:flex;flex-direction:column;gap:14px;">
        <section class="nf-pane">
          <div class="nf-section-head">
            <span>待审核事项</span>
            <span class="nf-pill warning">${pendingReviews.length} 待处理</span>
          </div>
          <div style="padding:12px;">
            ${pendingReviews.map((r) => `
              <div style="display:flex;flex-direction:column;gap:6px;">
                <div style="display:flex;align-items:center;gap:6px;">
                  <span class="nf-pill accent">Active ZIP 导入</span>
                  <span style="font-weight:600;">${r.itemTitle}</span>
                </div>
                <p class="nf-secondary" style="margin:0;font-size:12px;">${r.reason}</p>
                <div class="nf-muted nf-mono" style="font-size:11px;">待发布附件：${r.stagedAttachments.length} 个 · staging ${r.stagingId.slice(0, 8)}…</div>
                <div style="margin-top:4px;display:flex;gap:6px;">
                  <button class="nf-btn nf-btn-primary" style="height:26px;" data-goto="reviews">进入审核与预览</button>
                </div>
              </div>
            `).join("")}
          </div>
        </section>

        <section class="nf-pane">
          <div class="nf-section-head">
            <span>知识空间与实验状态</span>
            <button class="nf-btn" style="height:24px;font-size:11.5px;" data-goto="experiments">全部实验</button>
          </div>
          <div style="padding:10px 12px;display:flex;flex-direction:column;gap:10px;">
            ${DATA.spaces.map((s) => `
              <div style="display:flex;justify-content:space-between;align-items:center;font-size:12.5px;">
                <span style="display:flex;align-items:center;gap:7px;">${ICONS.folder} ${s.name}</span>
                <span class="nf-muted nf-mono">${s.count} 条目</span>
              </div>
            `).join("")}
            <div style="border-top:1px solid var(--nf-border-subtle);padding-top:10px;display:flex;flex-direction:column;gap:8px;">
              ${DATA.experiments.map((e) => `
                <div data-open-exp="${e.id}" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;">
                  <span class="nf-truncate" style="max-width:210px;">${e.title}</span>
                  <span class="nf-pill ${e.status === "active" ? "warning" : "success"}">${e.status === "active" ? "进行中" : "已完成"}</span>
                </div>
              `).join("")}
            </div>
          </div>
        </section>

        <section class="nf-pane">
          <div class="nf-section-head"><span>后端服务运行态（/api/health）</span><span class="nf-pill success">正常</span></div>
          <div style="padding:10px 12px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
            <div><span class="nf-muted">数据库</span><div class="nf-mono">sqlite · 已连接</div></div>
            <div><span class="nf-muted">模型适配层</span><div class="nf-mono">openai-compatible</div></div>
            <div><span class="nf-muted">向量通道</span><div class="nf-mono">configured (RRF)</div></div>
            <div><span class="nf-muted">GC / ORP 维护</span><div class="nf-mono">active (300s)</div></div>
          </div>
        </section>
      </div>
    </div>
  `;
}

function renderChat() {
  const conv = DATA.conversations.find((c) => c.id === state.selectedConversationId) || DATA.conversations[0];
  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">研究对话</span>
      <select class="nf-select" style="width:160px;">
        <option>全部知识空间</option>
        ${DATA.spaces.map((s) => `<option>${s.name}</option>`).join("")}
      </select>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="nf-btn" data-toast="已调用 POST /api/conversations/${conv.id}/extract 提取知识">${ICONS.knowledge} 从当前会话提取知识</button>
        <button class="nf-btn nf-btn-primary">${ICONS.plus} 新建会话</button>
      </div>
    </div>
    <div class="nf-split-2">
      <div class="nf-split-pane-left nf-scroll" style="overflow-y:auto;padding:8px;">
        ${DATA.conversations.map((c) => `
          <div data-open-conv="${c.id}" style="padding:9px 10px;border-radius:var(--nf-radius-sm);cursor:pointer;margin-bottom:4px;background:${c.id === conv.id ? "var(--nf-accent-soft)" : "transparent"};border:1px solid ${c.id === conv.id ? "var(--nf-accent-border)" : "transparent"};">
            <div style="font-weight:${c.id === conv.id ? "600" : "500"};font-size:12.5px;">${c.title}</div>
            <div class="nf-muted" style="font-size:11px;margin-top:3px;">${c.space} · ${c.updated}</div>
          </div>
        `).join("")}
      </div>
      <div class="nf-split-pane-main">
        <div class="nf-scroll" style="flex:1;overflow-y:auto;padding:18px 24px;display:flex;flex-direction:column;gap:14px;">
          ${conv.messages.map((m) => `
            <article class="nf-pane" style="padding:12px 14px;${m.role === "user" ? "background:var(--nf-bg-surface-subtle);" : ""}">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11.5px;">
                <span style="font-weight:600;color:${m.role === "user" ? "var(--nf-text-primary)" : "var(--nf-accent)"};">${m.role === "user" ? "研究员（你）" : "ExplainLab 助手 · deepseek-chat"}</span>
                <span class="nf-muted">${m.time}</span>
              </div>
              <div style="white-space:pre-wrap;font-size:13px;line-height:1.6;">${m.text}</div>
              ${m.sources ? `
                <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--nf-border-subtle);display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                  <span class="nf-muted" style="font-size:11px;">引用来源：</span>
                  ${m.sources.map((s) => `<span class="nf-pill accent">${ICONS.link} ${s}</span>`).join("")}
                  <button class="nf-btn" style="margin-left:auto;height:24px;font-size:11.5px;" data-toast="已复制回复文本">复制</button>
                  <button class="nf-btn" style="height:24px;font-size:11.5px;" data-toast="已触发知识提取">提取为知识</button>
                </div>
              ` : ""}
            </article>
          `).join("")}
        </div>
        <div style="padding:10px 18px 14px;border-top:1px solid var(--nf-border-subtle);background:var(--nf-bg-surface);display:flex;gap:8px;align-items:flex-end;">
          <textarea class="nf-textarea" rows="2" style="flex:1;" placeholder="输入研究问题…（Ctrl+Enter 发送，模型未配置时如实提示 503）"></textarea>
          <button class="nf-btn nf-btn-primary" style="height:34px;padding:0 16px;" data-toast="真实发送经 POST /api/conversations/{id}/chat">发送</button>
        </div>
      </div>
    </div>
  `;
}

function renderKnowledge() {
  const active = DATA.knowledge.find((k) => k.id === state.selectedKnowledgeId) || DATA.knowledge[0];
  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">知识库</span>
      <input class="nf-input" style="width:210px;" placeholder="筛选标题或标签…" />
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="nf-btn" data-toast="支持单篇 .md / 批量 .md / 含附件 .zip (Base64)">${ICONS.upload} 导入 MD / ZIP</button>
        <button class="nf-btn" data-toast="导出 ZIP（include_attachments=false，遵循后端契约）">${ICONS.download} 导出 ZIP</button>
        <button class="nf-btn nf-btn-primary">${ICONS.plus} 新建条目</button>
      </div>
    </div>
    <div class="nf-split-2" style="grid-template-columns:220px 1fr;">
      <div class="nf-split-pane-left nf-scroll" style="overflow-y:auto;padding:10px 8px;">
        <div class="nf-subnav-section">知识空间</div>
        ${DATA.spaces.map((s) => `
          <div class="nf-nav-item ${s.id === "sp-v2" ? "active" : ""}">
            ${ICONS.folder} <span class="nf-truncate">${s.name}</span>
            <span class="nf-nav-count">${s.count}</span>
          </div>
        `).join("")}
        <div class="nf-subnav-section" style="margin-top:10px;">标签索引</div>
        <div style="padding:4px 8px;display:flex;flex-wrap:wrap;gap:5px;">
          ${["batch-b", "postgresql", "lock", "gc", "orp", "import", "retrieval"].map((t) => `<span class="nf-pill">#${t}</span>`).join("")}
        </div>
      </div>
      <div class="nf-split-pane-main nf-scroll" style="overflow-y:auto;background:var(--nf-bg-surface);">
        <table class="nf-table">
          <thead>
            <tr>
              <th>知识标题</th>
              <th>状态</th>
              <th>标签</th>
              <th>附件</th>
              <th>双链</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            ${DATA.knowledge.map((k) => `
              <tr class="${k.id === active.id ? "selected" : ""}" data-select-knowledge="${k.id}">
                <td style="font-weight:500;">${k.title}</td>
                <td>${statusPill(k.status)}</td>
                <td>${k.tags.slice(0, 2).map((t) => `<span class="nf-pill" style="margin-right:4px;">${t}</span>`).join("")}</td>
                <td class="nf-mono nf-secondary">${k.attachments.length}</td>
                <td class="nf-mono nf-secondary">${k.links.length}/${k.backlinks.length}</td>
                <td class="nf-muted">${k.updated}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderSearch() {
  const selected = DATA.knowledge.find((k) => k.id === state.selectedSearchId) || DATA.knowledge[0];
  return `
    <div class="nf-toolbar" style="height:auto;padding:10px 14px;flex-wrap:wrap;">
      <input class="nf-input" style="flex:1;min-width:240px;" value="${state.searchQuery}" placeholder="输入关键词，跨会话与跨空间混合检索…" />
      <select class="nf-select"><option>全部空间</option><option>ExplainLab V2 架构</option><option>个人总知识库</option></select>
      <div class="nf-segmented">
        ${["hybrid", "fts", "vector"].map((m) => `<button class="${state.searchMode === m ? "active" : ""}" data-search-mode="${m}">${m === "hybrid" ? "混合 RRF" : m === "fts" ? "仅全文" : "仅向量"}</button>`).join("")}
      </div>
      <button class="nf-btn nf-btn-primary">${ICONS.search} 检索</button>
      <button class="nf-btn" data-toast="已调用 POST /api/search/reindex 重建全文与向量索引">${ICONS.refresh} 重建索引</button>
    </div>
    <div style="padding:7px 14px;background:var(--nf-bg-surface-subtle);border-bottom:1px solid var(--nf-border-subtle);font-size:12px;display:flex;align-items:center;gap:8px;">
      <span class="nf-pill success">embed_capability: supported</span>
      <span class="nf-secondary">全文（FTS / tsvector）+ 向量（BAAI/bge-m3）双通道 RRF(k=60) 融合排序 · 命中 3 条</span>
    </div>
    <div class="nf-split-2" style="grid-template-columns:1.05fr 1fr;">
      <div class="nf-split-pane-left nf-scroll" style="overflow-y:auto;padding:10px;background:var(--nf-bg-canvas);gap:8px;">
        ${DATA.knowledge.slice(0, 3).map((k, idx) => `
          <div class="nf-pane" data-select-search="${k.id}" style="padding:11px 12px;cursor:pointer;border-color:${k.id === selected.id ? "var(--nf-accent)" : "var(--nf-border-subtle)"};">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <span style="font-weight:600;">${k.title}</span>
              ${statusPill(k.status)}
            </div>
            <p class="nf-secondary" style="margin:6px 0 8px;font-size:12px;line-height:1.5;">${k.content.slice(0, 108)}…</p>
            <div style="display:flex;gap:6px;align-items:center;font-size:11px;" class="nf-mono">
              <span class="nf-pill accent">RRF ${(0.0328 - idx * 0.005).toFixed(4)}</span>
              <span class="nf-pill">全文 ${(0.0164 - idx * 0.002).toFixed(4)}</span>
              <span class="nf-pill">向量 ${(0.0164 - idx * 0.003).toFixed(4)}</span>
            </div>
          </div>
        `).join("")}
      </div>
      <div class="nf-split-pane-main nf-scroll" style="overflow-y:auto;padding:16px 20px;background:var(--nf-bg-surface);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h3 style="margin:0;font-size:15px;">${selected.title}</h3>
          ${statusPill(selected.status)}
        </div>
        <div style="display:flex;gap:6px;margin-bottom:12px;">
          ${selected.tags.map((t) => `<span class="nf-pill">#${t}</span>`).join("")}
        </div>
        <div style="white-space:pre-wrap;line-height:1.65;color:var(--nf-text-primary);">${selected.content}</div>
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--nf-border-subtle);display:flex;gap:8px;">
          <button class="nf-btn" data-open-knowledge="${selected.id}">在知识库中打开</button>
          <button class="nf-btn" data-toast="导出单篇 Markdown GET /api/knowledge/${selected.id}/markdown">${ICONS.download} 导出 Markdown</button>
        </div>
      </div>
    </div>
  `;
}

function renderMap() {
  const nodes = [
    { id: "k-103", title: "Active ZIP 导入审核流程", status: "draft", x: 110, y: 74, archived: false },
    { id: "k-101", title: "StorageKeyLock 双方言锁契约", status: "active", x: 380, y: 170, archived: false },
    { id: "k-102", title: "GC 七态状态机与隔离槽", status: "active", x: 110, y: 295, archived: false },
    { id: "k-104", title: "PostgreSQL 原生 tsvector 检索", status: "active", x: 470, y: 340, archived: false },
    { id: "k-105", title: "旧版单表全文索引草稿", status: "archived", x: 240, y: 425, archived: true },
  ].filter((n) => state.mapIncludeArchived || !n.archived);

  return `
    <div class="nf-map-stage">
      <!-- SVG Edges matching ELK layered layout & real relation visuals -->
      <svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;">
        <defs>
          <marker id="arr-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--nf-graph-edge-depends)"/>
          </marker>
          <marker id="arr-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--nf-graph-edge-refines)"/>
          </marker>
          <marker id="arr-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--nf-graph-edge-duplicate)"/>
          </marker>
        </defs>
        <path d="M 215 130 C 215 160, 480 140, 480 170" fill="none" stroke="var(--nf-graph-edge-depends)" stroke-width="1.8" marker-end="url(#arr-blue)"/>
        <path d="M 480 232 C 480 265, 215 260, 215 295" fill="none" stroke="var(--nf-graph-edge-depends)" stroke-width="1.8" marker-end="url(#arr-blue)"/>
        <path d="M 485 232 C 510 275, 570 295, 570 340" fill="none" stroke="var(--nf-graph-edge-refines)" stroke-width="1.8" marker-end="url(#arr-green)"/>
        ${state.mapIncludeArchived ? `<path d="M 345 425 C 400 410, 470 390, 520 398" fill="none" stroke="var(--nf-graph-edge-duplicate)" stroke-width="1.8" stroke-dasharray="6 4" marker-end="url(#arr-red)"/>` : ""}
      </svg>

      <!-- Floating Top-Left Toolbar (preserves 80%+ canvas area) -->
      <div class="nf-map-float" style="top:12px;left:12px;padding:6px 10px;display:flex;align-items:center;gap:8px;">
        <select class="nf-select" style="height:26px;"><option>全部空间</option><option>ExplainLab V2 架构</option></select>
        <label style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer;">
          <input type="checkbox" id="map-archived-toggle" ${state.mapIncludeArchived ? "checked" : ""} /> 显示归档
        </label>
        <button class="nf-btn" style="height:26px;">${ICONS.refresh} 重新布局 (ELK)</button>
        <span class="nf-muted nf-mono" style="font-size:11.5px;">节点 ${nodes.length} · 边 ${state.mapIncludeArchived ? 4 : 3}</span>
      </div>

      <!-- Nodes -->
      ${nodes.map((n) => `
        <div class="nf-map-node ${n.archived ? "archived" : ""} ${state.selectedMapNodeId === n.id ? "selected" : ""}" data-select-map-node="${n.id}" style="left:${n.x}px;top:${n.y}px;">
          <div style="font-weight:600;font-size:12.5px;" class="nf-truncate">${n.title}</div>
          <div style="margin-top:5px;display:flex;justify-content:space-between;align-items:center;">
            ${statusPill(n.status)}
            <span class="nf-muted nf-mono" style="font-size:10.5px;">${n.id}</span>
          </div>
        </div>
      `).join("")}

      <!-- Floating Bottom-Left Accurate SVG Legend (fixes solid-line bug!) -->
      <div class="nf-map-float" style="bottom:12px;left:12px;padding:6px 12px;display:flex;align-items:center;gap:12px;font-size:11.5px;">
        <span class="nf-muted">关系图例</span>
        <span style="display:inline-flex;align-items:center;gap:5px;"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="var(--nf-graph-edge-depends)" stroke-width="2"/></svg>依赖</span>
        <span style="display:inline-flex;align-items:center;gap:5px;"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="var(--nf-graph-edge-refines)" stroke-width="2"/></svg>细化</span>
        <span style="display:inline-flex;align-items:center;gap:5px;"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="var(--nf-graph-edge-duplicate)" stroke-width="2" stroke-dasharray="4 3"/></svg>重复（虚线）</span>
        <span style="display:inline-flex;align-items:center;gap:5px;"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="var(--nf-graph-edge-related)" stroke-width="2"/></svg>相关</span>
      </div>

      <!-- Floating Bottom-Right Zoom Controls -->
      <div class="nf-map-float" style="bottom:12px;right:12px;padding:4px;display:flex;gap:2px;">
        <button class="nf-icon-btn" title="缩小">−</button>
        <span class="nf-mono" style="font-size:11px;display:inline-flex;align-items:center;padding:0 6px;">100%</span>
        <button class="nf-icon-btn" title="放大">+</button>
      </div>
    </div>
  `;
}

function renderExperiments() {
  const exp = DATA.experiments.find((e) => e.id === state.selectedExperimentId) || DATA.experiments[0];
  let runnerHtml = "";
  if (exp.kind === "quiz") {
    const q = exp.questions[0];
    const picked = state.quizPicked[0];
    runnerHtml = `
      <div style="max-width:740px;display:flex;flex-direction:column;gap:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="nf-pill accent">知识测验 · 服务端即时判分</span>
          <span class="nf-muted nf-mono">第 1 / ${exp.questions.length} 题</span>
        </div>
        <div class="nf-pane" style="padding:16px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;line-height:1.55;">${q.prompt}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            ${q.options.map((opt, idx) => {
              const isCorrect = picked !== undefined && idx === q.correct;
              const isSelected = picked === idx;
              return `
                <button data-quiz-pick="${idx}" class="nf-btn" style="height:auto;padding:10px 12px;justify-content:flex-start;text-align:left;${isCorrect ? "border-color:var(--nf-status-success);background:var(--nf-status-success-bg);" : isSelected ? "border-color:var(--nf-accent);background:var(--nf-accent-soft);" : ""}">
                  <span class="nf-mono" style="font-weight:600;">${String.fromCharCode(65 + idx)}</span>
                  <span>${opt}</span>
                </button>
              `;
            }).join("")}
          </div>
          ${picked !== undefined ? `
            <div style="margin-top:12px;padding:10px 12px;border-radius:var(--nf-radius-sm);background:var(--nf-status-success-bg);border:1px solid rgba(15,157,117,0.28);">
              <div style="font-weight:600;color:var(--nf-status-success);">回答正确</div>
              <div style="margin-top:4px;font-size:12.5px;">${q.explanation}</div>
              <div class="nf-muted" style="margin-top:6px;font-size:11.5px;">来源知识：${q.sourceTitle}</div>
            </div>
          ` : ""}
        </div>
      </div>
    `;
  } else if (exp.kind === "compare") {
    const c = exp.compare;
    runnerHtml = `
      <div style="max-width:780px;display:flex;flex-direction:column;gap:12px;">
        <div class="nf-pane" style="padding:12px 14px;border-color:var(--nf-accent-border);background:var(--nf-accent-subtle);">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span class="nf-muted" style="font-size:11.5px;">关系判定</span>
            <span class="nf-pill accent">${c.relationType}</span>
          </div>
          <div style="font-size:13px;">${c.relationship}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div class="nf-pane" style="padding:12px;">
            <div style="font-weight:600;margin-bottom:8px;">相同点（${c.similarities.length}）</div>
            <ul style="margin:0;padding-left:16px;display:flex;flex-direction:column;gap:6px;">${c.similarities.map((s) => `<li>${s}</li>`).join("")}</ul>
          </div>
          <div class="nf-pane" style="padding:12px;">
            <div style="font-weight:600;margin-bottom:8px;">不同点（${c.differences.length}）</div>
            <ul style="margin:0;padding-left:16px;display:flex;flex-direction:column;gap:6px;">${c.differences.map((d) => `<li>${d}</li>`).join("")}</ul>
          </div>
        </div>
      </div>
    `;
  } else {
    runnerHtml = `
      <div style="max-width:680px;display:flex;flex-direction:column;gap:10px;">
        <div class="nf-pane" style="padding:10px 14px;background:var(--nf-status-success-bg);border-color:rgba(15,157,117,0.28);">
          确定性学习路径：沿「依赖 / 细化」关系 DFS 编排，无需模型，共 ${exp.steps.length} 步。
        </div>
        ${exp.steps.map((s) => `
          <div class="nf-pane" style="padding:12px 14px;display:flex;align-items:center;gap:12px;${s.goal ? "border-color:var(--nf-accent);" : ""}">
            <span class="nf-pill ${s.goal ? "accent" : ""}" style="width:26px;height:26px;justify-content:center;font-weight:600;">${s.pos}</span>
            <div style="flex:1;">
              <div style="font-weight:600;">${s.title}</div>
              <div class="nf-muted" style="font-size:11.5px;">${s.rel || "起点先修知识"}</div>
            </div>
            ${s.goal ? '<span class="nf-pill accent">目标知识</span>' : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">交互式知识实验</span>
      <span class="nf-muted" style="font-size:12px;">测验 / 对比（真实模型）· 学习路径（确定性）</span>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="nf-btn nf-btn-primary">${ICONS.plus} 新建实验</button>
      </div>
    </div>
    <div class="nf-split-2" style="grid-template-columns:280px 1fr;">
      <div class="nf-split-pane-left nf-scroll" style="overflow-y:auto;padding:10px 8px;">
        <div class="nf-subnav-section">实验会话（${DATA.experiments.length}）</div>
        ${DATA.experiments.map((e) => `
          <div data-open-exp="${e.id}" style="padding:10px;border-radius:var(--nf-radius-sm);cursor:pointer;margin-bottom:5px;background:${e.id === exp.id ? "var(--nf-accent-soft)" : "var(--nf-bg-surface)"};border:1px solid ${e.id === exp.id ? "var(--nf-accent-border)" : "var(--nf-border-subtle)"};">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <span class="nf-pill ${e.kind === "quiz" ? "warning" : e.kind === "compare" ? "accent" : "success"}">${e.kind === "quiz" ? "测验" : e.kind === "compare" ? "对比" : "路径"}</span>
              <span class="nf-muted nf-mono" style="font-size:11px;">${e.createdAt}</span>
            </div>
            <div style="font-weight:600;font-size:12.5px;">${e.title}</div>
            <div class="nf-muted" style="font-size:11px;margin-top:3px;">${e.status === "active" ? "进行中" : "已完成"} · ${e.itemCount} 条知识</div>
          </div>
        `).join("")}
      </div>
      <div class="nf-split-pane-main nf-scroll" style="overflow-y:auto;padding:18px 22px;">
        ${runnerHtml}
      </div>
    </div>
  `;
}

function renderReviews() {
  const rev = DATA.reviews.find((r) => r.id === state.selectedReviewId) || DATA.reviews[0];
  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">审核队列</span>
      <div class="nf-segmented">
        ${["all", "pending", "approved", "rejected"].map((f) => `<button class="${state.reviewFilter === f ? "active" : ""}" data-review-filter="${f}">${f === "all" ? "全部" : f === "pending" ? "待审核 (1)" : f === "approved" ? "已批准" : "已驳回"}</button>`).join("")}
      </div>
      <span class="nf-muted" style="margin-left:auto;font-size:12px;">遵循 V2 B4 契约：业务提交与独立索引 Session 分离</span>
    </div>
    <div class="nf-split-2" style="grid-template-columns:290px 1fr;">
      <div class="nf-split-pane-left nf-scroll" style="overflow-y:auto;padding:8px;">
        ${DATA.reviews.filter((r) => state.reviewFilter === "all" || r.status === state.reviewFilter).map((r) => `
          <div data-select-review="${r.id}" style="padding:10px;border-radius:var(--nf-radius-sm);cursor:pointer;margin-bottom:6px;background:${r.id === rev.id ? "var(--nf-accent-soft)" : "var(--nf-bg-surface)"};border:1px solid ${r.id === rev.id ? "var(--nf-accent-border)" : "var(--nf-border-subtle)"};">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <span class="nf-pill ${r.isZipImport ? "accent" : ""}">${r.isZipImport ? "Active ZIP 导入" : "合并重复"}</span>
              ${statusPill(r.status)}
            </div>
            <div style="font-weight:600;font-size:12.5px;">${r.itemTitle}</div>
            <div class="nf-muted" style="font-size:11px;margin-top:3px;">${r.createdAt}</div>
          </div>
        `).join("")}
      </div>
      <div class="nf-split-pane-main nf-scroll" style="overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:14px;">
        <div class="nf-pane" style="padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="display:flex;align-items:center;gap:8px;">
              <h3 style="margin:0;font-size:15px;">${rev.itemTitle}</h3>
              ${statusPill(rev.status)}
            </div>
            <span class="nf-muted nf-mono" style="font-size:11.5px;">${rev.id} · item ${rev.itemId}</span>
          </div>
          <p class="nf-secondary" style="margin:8px 0 0;font-size:12.5px;">${rev.reason}</p>
        </div>

        <section class="nf-pane" style="padding:14px;">
          <div style="font-weight:600;margin-bottom:8px;">正文差异比较</div>
          <div class="nf-diff">
            <div class="nf-diff-line nf-diff-del">${rev.diffOld}</div>
            <div class="nf-diff-line nf-diff-add">${rev.diffNew}</div>
          </div>
        </section>

        ${rev.isZipImport ? `
          <section class="nf-pane" style="overflow:hidden;">
            <div class="nf-section-head">
              <span>V2 Active ZIP 导入 Manifest & 待发布附件清单</span>
              <span class="nf-mono nf-muted" style="font-size:11px;white-space:nowrap;">staging: ${rev.stagingId.slice(0, 8)}… · digest verified</span>
            </div>
            <div class="nf-scroll" style="overflow-x:auto;">
            <table class="nf-table">
              <thead><tr><th>Ordinal</th><th>显示文件名</th><th>MIME</th><th>大小</th><th>SHA-256</th></tr></thead>
              <tbody>
                ${rev.stagedAttachments.map((a) => `
                  <tr>
                    <td class="nf-mono">${a.ordinal}</td>
                    <td style="font-weight:500;">${a.filename}</td>
                    <td class="nf-mono nf-secondary">${a.mime}</td>
                    <td class="nf-mono">${a.size}</td>
                    <td class="nf-mono nf-muted">${a.sha256}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
            </div>
          </section>
        ` : ""}

        ${rev.status === "pending" ? `
          <section class="nf-pane" style="padding:14px;display:flex;flex-direction:column;gap:10px;">
            <label style="font-weight:600;font-size:12.5px;">审批备注（ReviewResolve.note）</label>
            <input class="nf-input" placeholder="可选：输入批准或驳回说明…" />
            <div style="display:flex;gap:8px;">
              <button class="nf-btn nf-btn-primary" data-toast="POST /api/reviews/${rev.id}/approve：发布正式 blob → 提交业务事务 → 独立 Session 同步索引">批准并发布附件</button>
              <button class="nf-btn nf-btn-danger" data-toast="POST /api/reviews/${rev.id}/reject：拒绝后安全清理可证实归属的 staging">驳回变更</button>
            </div>
          </section>
        ` : ""}
      </div>
    </div>
  `;
}

function renderThemeStudio() {
  const effectiveTheme = document.documentElement.getAttribute("data-theme");
  return `
    <div class="nf-toolbar">
      <span class="nf-toolbar-title">Theme Studio · Nesti Fluent</span>
      <div class="nf-segmented">
        <button class="${state.themeStudioTab === "studio" ? "active" : ""}" data-studio-tab="studio">主题引擎</button>
        <button class="${state.themeStudioTab === "components" ? "active" : ""}" data-studio-tab="components">组件状态矩阵 (10 态)</button>
      </div>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="nf-btn" id="btn-export-theme">${ICONS.download} 导出主题 JSON</button>
        <button class="nf-btn" id="btn-reset-theme">${ICONS.refresh} 恢复默认</button>
      </div>
    </div>
    ${state.themeStudioTab === "components" ? renderComponentMatrix() : `
    <div class="nf-scroll" style="flex:1;overflow-y:auto;padding:16px 20px;display:grid;grid-template-columns:1.15fr 1fr;gap:16px;align-content:start;">
      <div style="display:flex;flex-direction:column;gap:14px;">
        <section class="nf-pane" style="padding:14px;display:flex;flex-direction:column;gap:12px;">
          <div style="font-weight:600;">外观模式（Appearance）</div>
          <div class="nf-segmented" style="width:fit-content;">
            ${[["light", "浅色模式"], ["dark", "深色模式"], ["system", "跟随系统"]].map(([k, l]) => `<button class="${state.themeMode === k ? "active" : ""}" data-set-theme-mode="${k}">${l}</button>`).join("")}
          </div>

          <div style="font-weight:600;margin-top:4px;">六套官方预设主题</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
            ${PRESETS.map((p) => `
              <button data-set-preset="${p.id}" style="padding:10px;border-radius:var(--nf-radius-md);border:1px solid ${state.preset === p.id ? "var(--nf-accent)" : "var(--nf-border-subtle)"};background:${state.preset === p.id ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)"};cursor:pointer;text-align:left;">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
                  <span style="width:14px;height:14px;border-radius:50%;background:${p.primary};display:inline-block;"></span>
                  <span style="width:14px;height:14px;border-radius:50%;background:${p.secondary};display:inline-block;"></span>
                </div>
                <div style="font-weight:600;font-size:12px;">${p.name}</div>
                <div class="nf-muted" style="font-size:11px;">${p.desc}</div>
              </button>
            `).join("")}
          </div>

          <div style="display:flex;align-items:center;gap:10px;padding-top:6px;border-top:1px solid var(--nf-border-subtle);">
            <span style="font-weight:600;">自定义强调色</span>
            <input type="color" id="custom-accent-picker" value="${state.customAccent}" style="width:32px;height:26px;border:1px solid var(--nf-border-default);border-radius:4px;cursor:pointer;background:transparent;" />
            <span class="nf-mono nf-muted" style="font-size:12px;">${state.preset === "custom" ? state.customAccent : "当前使用预设"}</span>
          </div>
        </section>

        <section class="nf-pane" style="padding:14px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
          <div>
            <div style="font-weight:600;margin-bottom:6px;">界面密度</div>
            <div class="nf-segmented">
              ${[["compact", "紧凑"], ["comfortable", "标准"], ["spacious", "宽松"]].map(([k, l]) => `<button class="${state.density === k ? "active" : ""}" data-set-density="${k}">${l}</button>`).join("")}
            </div>
          </div>
          <div>
            <div style="font-weight:600;margin-bottom:6px;">圆角风格</div>
            <div class="nf-segmented">
              ${[["sharp", "锐利"], ["balanced", "均衡"], ["soft", "柔和"]].map(([k, l]) => `<button class="${state.radius === k ? "active" : ""}" data-set-radius="${k}">${l}</button>`).join("")}
            </div>
          </div>
          <div>
            <div style="font-weight:600;margin-bottom:6px;">阴影层级</div>
            <div class="nf-segmented">
              ${[["none", "扁平"], ["subtle", "克制"], ["elevated", "立体"]].map(([k, l]) => `<button class="${state.shadow === k ? "active" : ""}" data-set-shadow="${k}">${l}</button>`).join("")}
            </div>
          </div>
        </section>
      </div>

      <div style="display:flex;flex-direction:column;gap:14px;">
        <section class="nf-pane" style="padding:14px;display:flex;flex-direction:column;gap:10px;">
          <div style="font-weight:600;">品牌与图标联动保护规则</div>
          <div style="display:flex;align-items:center;gap:12px;padding:10px;border-radius:var(--nf-radius-sm);background:var(--nf-bg-surface-subtle);border:1px solid var(--nf-border-subtle);">
            <span class="nf-nesti-logo-slot" style="width:34px;height:34px;font-size:14px;" title="原版 Nesti 品牌图标占位槽（仓库暂无原图，待官方资源落位）">N</span>
            <div>
              <div style="font-weight:600;">原版 Nesti Logo（永久锁定）</div>
              <div class="nf-muted" style="font-size:11.5px;">不随主题强调色染色；当前工作区暂无原图文件，保留官方资产槽位。</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;padding:10px;border-radius:var(--nf-radius-sm);background:var(--nf-accent-soft);border:1px solid var(--nf-accent-border);">
            <span style="width:34px;height:34px;border-radius:var(--nf-radius-sm);background:var(--nf-bg-surface);color:var(--nf-module-icon);display:inline-flex;align-items:center;justify-content:center;">${ICONS.knowledge}</span>
            <div>
              <div style="font-weight:600;">ExplainLab 模块图标（自动联动）</div>
              <div class="nf-secondary" style="font-size:11.5px;">使用 <span class="nf-mono">var(--nf-module-icon)</span>，随 6 套主题与自定义强调色实时变化。</div>
            </div>
          </div>
          <div style="padding:10px;border-radius:var(--nf-radius-sm);background:var(--nf-bg-surface-subtle);border:1px dashed var(--nf-border-default);font-size:11.5px;" class="nf-secondary">
            <strong>Windows 系统级联动（规划边界）</strong>：快捷方式、任务栏图标与系统托盘联动需在未来 Tauri 2 桌面宿主阶段通过 Win32 / ICO 图标集与系统主题事件实现，本设计稿明确区分 Web 主题层与 OS 宿主层，不伪称已实现系统级功能。
          </div>
        </section>

        <section class="nf-pane" style="padding:14px;">
          <div style="font-weight:600;margin-bottom:8px;">实时主题配置快照（JSON）</div>
          <pre class="nf-mono" style="margin:0;padding:10px;border-radius:var(--nf-radius-sm);background:var(--nf-bg-surface-subtle);font-size:11.5px;overflow-x:auto;">${JSON.stringify({
            schema: "nesti.fluent.theme/v1",
            mode: state.themeMode,
            resolved: effectiveTheme,
            preset: state.preset,
            density: state.density,
            radius: state.radius,
            shadow: state.shadow,
          }, null, 2)}</pre>
        </section>
      </div>
    </div>
    `}
  `;
}

function renderComponentMatrix() {
  return `
    <div class="nf-scroll" style="flex:1;overflow-y:auto;padding:16px 20px;display:grid;grid-template-columns:1fr 1fr;gap:14px;align-content:start;">
      <section class="nf-pane" style="padding:14px;display:flex;flex-direction:column;gap:10px;">
        <div style="font-weight:600;">按钮与交互态（Normal / Primary / Active / Disabled / Danger）</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
          <button class="nf-btn">默认按钮</button>
          <button class="nf-btn nf-btn-primary">主操作按钮</button>
          <button class="nf-btn" style="background:var(--nf-accent-soft);border-color:var(--nf-accent-border);color:var(--nf-accent);">Selected / Active</button>
          <button class="nf-btn" disabled>Disabled</button>
          <button class="nf-btn nf-btn-danger">危险操作</button>
        </div>
        <div style="font-weight:600;margin-top:6px;">输入控件与焦点态</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
          <input class="nf-input" placeholder="正常输入状态" />
          <input class="nf-input" value="聚焦状态示例" style="border-color:var(--nf-accent);box-shadow:0 0 0 2px var(--nf-accent-subtle);" />
        </div>
      </section>

      <section class="nf-pane" style="padding:14px;display:flex;flex-direction:column;gap:8px;">
        <div style="font-weight:600;">反馈状态（Loading / Empty / Error / Confirmation / Success）</div>
        <div style="padding:8px 10px;border-radius:var(--nf-radius-sm);background:var(--nf-bg-surface-subtle);border:1px solid var(--nf-border-subtle);font-size:12px;">Loading · 正在同步知识索引与存储锁状态…</div>
        <div style="padding:8px 10px;border-radius:var(--nf-radius-sm);border:1px dashed var(--nf-border-default);font-size:12px;" class="nf-muted">Empty · 当前空间暂无附件，支持拖放或选择文件（≤10 MiB，8 类白名单 MIME）</div>
        <div style="padding:8px 10px;border-radius:var(--nf-radius-sm);background:var(--nf-status-danger-bg);color:var(--nf-status-danger);font-size:12px;">Error · ATTACHMENT_ITEM_ARCHIVED：已归档条目禁止上传新附件</div>
        <div style="padding:8px 10px;border-radius:var(--nf-radius-sm);background:var(--nf-status-warning-bg);color:var(--nf-status-warning);font-size:12px;display:flex;justify-content:space-between;align-items:center;">
          <span>Confirmation · 确认删除最后一条引用并安排 GC 隔离？</span>
          <button class="nf-btn nf-btn-danger" style="height:22px;font-size:11px;">确认</button>
        </div>
        <div style="padding:8px 10px;border-radius:var(--nf-radius-sm);background:var(--nf-status-success-bg);color:var(--nf-status-success);font-size:12px;">Success · 审批已提交，正式附件已发布至内容寻址存储</div>
      </section>
    </div>
  `;
}

function renderInspector() {
  if (state.page === "knowledge" || state.page === "map") {
    const id = state.page === "map" ? state.selectedMapNodeId : state.selectedKnowledgeId;
    const item = DATA.knowledge.find((k) => k.id === id) || DATA.knowledge[0];
    return `
      <div class="nf-inspector-header">
        <span>检查器 · 知识详情</span>
        <button class="nf-icon-btn" id="btn-close-inspector">${ICONS.close}</button>
      </div>
      <div class="nf-inspector-body nf-scroll">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
            <div style="font-weight:600;font-size:13.5px;">${item.title}</div>
            ${statusPill(item.status)}
          </div>
          <div class="nf-muted nf-mono" style="font-size:11px;margin-top:4px;">${item.id} · 更新于 ${item.updated}</div>
        </div>
        <div class="nf-segmented" style="width:100%;justify-content:space-between;">
          ${[["preview", "正文"], ["attachments", `附件(${item.attachments.length})`], ["links", "双链"], ["governance", "版本"]].map(([k, l]) => `<button style="flex:1;" class="${state.knowledgeInspectorTab === k ? "active" : ""}" data-insp-tab="${k}">${l}</button>`).join("")}
        </div>
        ${state.knowledgeInspectorTab === "preview" ? `
          <div style="white-space:pre-wrap;font-size:12.5px;line-height:1.6;">${item.content}</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px;">${item.tags.map((t) => `<span class="nf-pill">#${t}</span>`).join("")}</div>
        ` : state.knowledgeInspectorTab === "attachments" ? `
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${item.attachments.length === 0 ? '<div class="nf-muted" style="font-size:12px;">暂无附件。支持 JSON Base64 上传（≤10 MiB，禁止 SVG）。</div>' : item.attachments.map((a) => `
              <div style="padding:8px 10px;border:1px solid var(--nf-border-subtle);border-radius:var(--nf-radius-sm);">
                <div style="font-weight:500;display:flex;align-items:center;gap:6px;">${ICONS.paperclip} ${a.filename}</div>
                <div class="nf-muted nf-mono" style="font-size:11px;margin-top:3px;">${a.mime} · ${a.size} · ${a.hash}</div>
              </div>
            `).join("")}
            <button class="nf-btn" data-toast="POST /api/knowledge/${item.id}/attachments (JSON Base64)">${ICONS.upload} 上传附件</button>
          </div>
        ` : state.knowledgeInspectorTab === "links" ? `
          <div style="display:flex;flex-direction:column;gap:10px;font-size:12px;">
            <div>
              <div class="nf-muted" style="margin-bottom:4px;">出链（GET /links）</div>
              ${item.links.length ? item.links.map((l) => `<div class="nf-pill accent">${ICONS.link} ${l.target}</div>`).join("") : '<span class="nf-muted">无出链</span>'}
            </div>
            <div>
              <div class="nf-muted" style="margin-bottom:4px;">反向链接（GET /backlinks）</div>
              ${item.backlinks.length ? item.backlinks.map((b) => `<div class="nf-pill">${ICONS.link} ${b.source}</div>`).join("") : '<span class="nf-muted">无反链</span>'}
            </div>
          </div>
        ` : `
          <div style="display:flex;flex-direction:column;gap:8px;font-size:12px;">
            ${item.versions.map((v) => `
              <div style="padding:8px;border:1px solid var(--nf-border-subtle);border-radius:var(--nf-radius-sm);display:flex;justify-content:space-between;align-items:center;">
                <div><div style="font-weight:600;">v${v.v} · ${v.summary}</div><div class="nf-muted" style="font-size:11px;">${v.at}</div></div>
                <button class="nf-btn" style="height:24px;font-size:11px;">回滚</button>
              </div>
            `).join("")}
          </div>
        `}
      </div>
    `;
  }

  return `
    <div class="nf-inspector-header">
      <span>上下文检查器</span>
      <button class="nf-icon-btn" id="btn-close-inspector">${ICONS.close}</button>
    </div>
    <div class="nf-inspector-body nf-scroll">
      <div>
        <div class="nf-muted" style="font-size:11px;margin-bottom:6px;">运行态（真实 API 契约）</div>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:12px;">
          <div style="display:flex;justify-content:space-between;"><span>模型</span><span class="nf-mono">deepseek-chat</span></div>
          <div style="display:flex;justify-content:space-between;"><span>向量</span><span class="nf-mono">BAAI/bge-m3</span></div>
          <div style="display:flex;justify-content:space-between;"><span>存储锁</span><span class="nf-mono">SQLite / PG</span></div>
        </div>
      </div>
      <div style="border-top:1px solid var(--nf-border-subtle);padding-top:10px;">
        <div class="nf-muted" style="font-size:11px;margin-bottom:6px;">Nesti Shell 边界说明</div>
        <p class="nf-secondary" style="margin:0;font-size:12px;line-height:1.55;">右侧检查器按需开关，不强制占用所有页面。点击顶栏右侧检查器图标可随时折叠，释放完整工作区宽度。</p>
      </div>
    </div>
  `;
}

function render() {
  applyThemeTokens();
  const root = document.getElementById("app");
  const showInspector = state.inspectorOpen && !["dashboard", "theme-studio", "search", "experiments"].includes(state.page);
  const currentNav = NAV_PAGES.find((p) => p.id === state.page);
  const pageTitle = state.page === "theme-studio" ? "Theme Studio" : currentNav ? currentNav.label : "ExplainLab";

  let mainContent = "";
  if (state.page === "dashboard") mainContent = renderDashboard();
  else if (state.page === "chat") mainContent = renderChat();
  else if (state.page === "knowledge") mainContent = renderKnowledge();
  else if (state.page === "search") mainContent = renderSearch();
  else if (state.page === "map") mainContent = renderMap();
  else if (state.page === "experiments") mainContent = renderExperiments();
  else if (state.page === "reviews") mainContent = renderReviews();
  else if (state.page === "theme-studio") mainContent = renderThemeStudio();

  root.innerHTML = `
    <!-- 1. Application Titlebar (Nesti Workspace Shell) -->
    <header class="nf-titlebar">
      <div class="nf-brand-group">
        <button class="nf-icon-btn" id="btn-toggle-subnav" title="折叠/展开次级导航">${ICONS.panelLeft}</button>
        <span class="nf-nesti-logo-slot" data-slot="nesti-brand-logo" title="原版 Nesti 蓝白图标官方资产槽位（当前仓库暂无原图，严禁重绘替代）">N</span>
        <span class="nf-brand-title">
          <span>Nesti</span>
          <span class="nf-brand-sep">/</span>
          <span class="nf-brand-module">ExplainLab</span>
        </span>
      </div>

      <button class="nf-global-search-trigger" id="btn-open-command">
        ${ICONS.search}
        <span>全局搜索知识、会话或命令…</span>
        <span class="nf-kbd">Ctrl K</span>
      </button>

      <div class="nf-titlebar-actions">
        <button class="nf-icon-btn" id="btn-quick-theme" title="切换浅色/深色主题">${document.documentElement.getAttribute("data-theme") === "dark" ? ICONS.sun : ICONS.moon}</button>
        <button class="nf-icon-btn ${state.page === "theme-studio" ? "active" : ""}" data-goto="theme-studio" title="Theme Studio">${ICONS.palette}</button>
        <button class="nf-icon-btn" data-goto="reviews" title="待审核通知（1）">${ICONS.bell}<span class="nf-badge-dot"></span></button>
        <button class="nf-icon-btn ${showInspector ? "active" : ""}" id="btn-toggle-inspector" title="切换右侧检查器">${ICONS.panelRight}</button>
        <button class="nf-icon-btn" title="本地工作区用户">${ICONS.user}</button>
        <div class="nf-window-controls" aria-hidden="true">
          <button class="nf-icon-btn" style="width:26px;">─</button>
          <button class="nf-icon-btn" style="width:26px;">□</button>
          <button class="nf-icon-btn" style="width:26px;">${ICONS.close}</button>
        </div>
      </div>
    </header>

    <!-- 2. Workspace Body -->
    <div class="nf-body">
      <!-- Nesti Shell Primary Rail -->
      <nav class="nf-rail" aria-label="Nesti 主模块导航">
        <button class="nf-rail-btn" title="Desktop Hub（未来 Nesti 模块）" data-toast="Desktop Hub 属于未来 Nesti 宿主生态">${ICONS.hub}</button>
        <button class="nf-rail-btn active" title="ExplainLab 知识工作区" data-goto="dashboard">${ICONS.knowledge}</button>
        <button class="nf-rail-btn" title="Agent Center（未来 Nesti 模块）" data-toast="Agent Center 属于未来 Nesti 宿主生态">${ICONS.agent}</button>
        <div class="nf-rail-spacer"></div>
        <button class="nf-rail-btn ${state.page === "theme-studio" ? "active" : ""}" title="Theme Studio & 组件规范" data-goto="theme-studio">${ICONS.palette}</button>
      </nav>

      <!-- ExplainLab Secondary Module Navigation -->
      <aside class="nf-subnav nf-scroll ${state.subnavOpen ? "" : "collapsed"}" aria-label="ExplainLab 业务导航">
        <div class="nf-subnav-section">ExplainLab V2</div>
        ${NAV_PAGES.map((p) => `
          <button class="nf-nav-item ${state.page === p.id ? "active" : ""}" data-goto="${p.id}">
            ${ICONS[p.icon]}
            <span>${p.label}</span>
            ${p.count ? `<span class="nf-nav-count">${p.count}</span>` : ""}
          </button>
        `).join("")}
        <div class="nf-subnav-section" style="margin-top:8px;">外观与规范</div>
        <button class="nf-nav-item ${state.page === "theme-studio" && state.themeStudioTab === "studio" ? "active" : ""}" data-goto-studio="studio">${ICONS.palette}<span>Theme Studio</span></button>
        <button class="nf-nav-item ${state.page === "theme-studio" && state.themeStudioTab === "components" ? "active" : ""}" data-goto-studio="components">${ICONS.layers}<span>组件状态规范</span></button>
      </aside>

      <!-- Main Workspace Column -->
      <div class="nf-workspace-col">
        <div class="nf-tabbar">
          <button class="nf-tab active">${ICONS[currentNav ? currentNav.icon : "palette"]} <span>${pageTitle}</span></button>
          <button class="nf-tab" data-goto="knowledge">${ICONS.knowledge} <span>StorageKeyLock 双方言锁契约</span></button>
          <button class="nf-tab" data-goto="reviews">${ICONS.reviews} <span>Active ZIP 审核 #rev-01</span></button>
        </div>
        <main class="nf-main">${mainContent}</main>
      </div>

      <!-- Collapsible Right Inspector -->
      <aside class="nf-inspector ${showInspector ? "" : "hidden"}">${renderInspector()}</aside>
    </div>

    <!-- 3. Bottom Status Bar -->
    <footer class="nf-statusbar">
      <span><span class="nf-status-dot"></span>Backend 127.0.0.1:8000 · SQLite (FTS5 + RRF)</span>
      <span class="nf-muted">Model: openai-compatible · Embed: configured</span>
      <div class="nf-status-right">
        <span class="nf-mono">Theme: ${state.preset} (${document.documentElement.getAttribute("data-theme")})</span>
        <span class="nf-mono">ExplainLab V2 · Nesti Fluent</span>
      </div>
    </footer>

    <!-- Ctrl+K Global Command Modal -->
    <div class="nf-modal-backdrop ${state.commandOpen ? "" : "hidden"}" id="command-modal">
      <div class="nf-command-box">
        <div style="padding:10px 12px;border-bottom:1px solid var(--nf-border-subtle);display:flex;align-items:center;gap:8px;">
          ${ICONS.search}
          <input class="nf-input" id="command-input" style="flex:1;border:none;box-shadow:none;" placeholder="跳转到页面、搜索知识条目或切换主题…" />
          <span class="nf-kbd">ESC</span>
        </div>
        <div style="padding:6px;">
          ${NAV_PAGES.map((p) => `<div class="nf-nav-item" data-goto="${p.id}">${ICONS[p.icon]} <span>跳转至 ${p.label}</span></div>`).join("")}
        </div>
      </div>
    </div>

    ${state.toast ? `<div style="position:fixed;right:16px;bottom:38px;padding:8px 14px;border-radius:var(--nf-radius-md);background:var(--nf-text-primary);color:var(--nf-bg-surface);font-size:12px;box-shadow:var(--nf-shadow-lg);z-index:200;">${state.toast}</div>` : ""}
  `;

  bindEvents();
}

function showToast(msg) {
  state.toast = msg;
  render();
  setTimeout(() => {
    if (state.toast === msg) {
      state.toast = null;
      render();
    }
  }, 2600);
}

function bindEvents() {
  document.querySelectorAll("[data-goto]").forEach((el) =>
    el.addEventListener("click", () => {
      state.page = el.getAttribute("data-goto");
      state.commandOpen = false;
      render();
    })
  );
  document.querySelectorAll("[data-goto-studio]").forEach((el) =>
    el.addEventListener("click", () => {
      state.page = "theme-studio";
      state.themeStudioTab = el.getAttribute("data-goto-studio");
      render();
    })
  );
  document.querySelectorAll("[data-studio-tab]").forEach((el) =>
    el.addEventListener("click", () => {
      state.themeStudioTab = el.getAttribute("data-studio-tab");
      render();
    })
  );
  document.querySelectorAll("[data-open-knowledge]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedKnowledgeId = el.getAttribute("data-open-knowledge");
      state.page = "knowledge";
      state.inspectorOpen = true;
      render();
    })
  );
  document.querySelectorAll("[data-select-knowledge]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedKnowledgeId = el.getAttribute("data-select-knowledge");
      state.inspectorOpen = true;
      render();
    })
  );
  document.querySelectorAll("[data-insp-tab]").forEach((el) =>
    el.addEventListener("click", () => {
      state.knowledgeInspectorTab = el.getAttribute("data-insp-tab");
      render();
    })
  );
  document.querySelectorAll("[data-open-conv]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedConversationId = el.getAttribute("data-open-conv");
      state.page = "chat";
      render();
    })
  );
  document.querySelectorAll("[data-select-search]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedSearchId = el.getAttribute("data-select-search");
      render();
    })
  );
  document.querySelectorAll("[data-search-mode]").forEach((el) =>
    el.addEventListener("click", () => {
      state.searchMode = el.getAttribute("data-search-mode");
      render();
    })
  );
  document.querySelectorAll("[data-select-map-node]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedMapNodeId = el.getAttribute("data-select-map-node");
      state.inspectorOpen = true;
      render();
    })
  );
  document.getElementById("map-archived-toggle")?.addEventListener("change", (e) => {
    state.mapIncludeArchived = e.target.checked;
    render();
  });
  document.querySelectorAll("[data-open-exp]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedExperimentId = el.getAttribute("data-open-exp");
      state.page = "experiments";
      render();
    })
  );
  document.querySelectorAll("[data-quiz-pick]").forEach((el) =>
    el.addEventListener("click", () => {
      state.quizPicked[0] = Number(el.getAttribute("data-quiz-pick"));
      render();
    })
  );
  document.querySelectorAll("[data-select-review]").forEach((el) =>
    el.addEventListener("click", () => {
      state.selectedReviewId = el.getAttribute("data-select-review");
      render();
    })
  );
  document.querySelectorAll("[data-review-filter]").forEach((el) =>
    el.addEventListener("click", () => {
      state.reviewFilter = el.getAttribute("data-review-filter");
      render();
    })
  );
  document.querySelectorAll("[data-set-theme-mode]").forEach((el) =>
    el.addEventListener("click", () => {
      state.themeMode = el.getAttribute("data-set-theme-mode");
      render();
    })
  );
  document.querySelectorAll("[data-set-preset]").forEach((el) =>
    el.addEventListener("click", () => {
      state.preset = el.getAttribute("data-set-preset");
      render();
    })
  );
  document.querySelectorAll("[data-set-density]").forEach((el) =>
    el.addEventListener("click", () => {
      state.density = el.getAttribute("data-set-density");
      render();
    })
  );
  document.querySelectorAll("[data-set-radius]").forEach((el) =>
    el.addEventListener("click", () => {
      state.radius = el.getAttribute("data-set-radius");
      render();
    })
  );
  document.querySelectorAll("[data-set-shadow]").forEach((el) =>
    el.addEventListener("click", () => {
      state.shadow = el.getAttribute("data-set-shadow");
      render();
    })
  );
  document.getElementById("custom-accent-picker")?.addEventListener("input", (e) => {
    state.customAccent = e.target.value;
    state.preset = "custom";
    render();
  });
  document.getElementById("btn-reset-theme")?.addEventListener("click", () => {
    Object.assign(state, { themeMode: "light", preset: "glacier", density: "comfortable", radius: "balanced", shadow: "subtle" });
    showToast("已恢复 Nesti Fluent 默认主题（Glacier Blue / 浅色）");
  });
  document.getElementById("btn-export-theme")?.addEventListener("click", () => {
    showToast("已生成 nesti.fluent.theme/v1 JSON 快照");
  });
  document.getElementById("btn-toggle-subnav")?.addEventListener("click", () => {
    state.subnavOpen = !state.subnavOpen;
    render();
  });
  document.getElementById("btn-toggle-inspector")?.addEventListener("click", () => {
    state.inspectorOpen = !state.inspectorOpen;
    render();
  });
  document.getElementById("btn-close-inspector")?.addEventListener("click", () => {
    state.inspectorOpen = false;
    render();
  });
  document.getElementById("btn-quick-theme")?.addEventListener("click", () => {
    state.themeMode = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    render();
  });
  document.getElementById("btn-open-command")?.addEventListener("click", () => {
    state.commandOpen = true;
    render();
  });
  document.getElementById("command-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "command-modal") {
      state.commandOpen = false;
      render();
    }
  });
  document.querySelectorAll("[data-toast]").forEach((el) =>
    el.addEventListener("click", () => showToast(el.getAttribute("data-toast")))
  );
}

window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    state.commandOpen = !state.commandOpen;
    render();
  } else if (e.key === "Escape" && state.commandOpen) {
    state.commandOpen = false;
    render();
  }
});

render();
