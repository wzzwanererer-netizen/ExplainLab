import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  AnalyzeResponse,
  AttachmentItem,
  KnowledgeItem,
  KnowledgeRelation,
  KnowledgeVersion,
  LinkItem,
  RelationOrigin,
  RelationType,
} from "../api/types";

const RELATION_LABEL: Record<RelationType, string> = {
  related: "相关",
  depends_on: "依赖",
  duplicate_of: "重复",
  refines: "细化",
  contradicts: "矛盾",
};

const ORIGIN_LABEL: Record<RelationOrigin, string> = {
  manual: "人工",
  llm: "模型推断",
  dedup: "去重",
};

const SOURCE_LABEL: Record<string, string> = {
  conversation: "对话",
  document: "文档",
  manual: "手动",
  import: "导入",
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

interface Props {
  item: KnowledgeItem;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onChanged: () => void;
  onNavigateItem?: (itemId: string) => void;
}

/**
 * 知识条目治理详情（M2）：关系 / 版本 / 来源三个分区，
 * 查重分析（词面 + 模型）、合并重复（提交审核）、版本回滚。
 * 全部数据来自后端真实 API；模型未配置时如实显示错误。
 */
export function KnowledgeDetail({
  item,
  onNotice,
  onError,
  onChanged,
  onNavigateItem,
}: Props) {
  const [relations, setRelations] = useState<KnowledgeRelation[]>([]);
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [links, setLinks] = useState<LinkItem[]>([]);
  const [backlinks, setBacklinks] = useState<LinkItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadGovernance = useCallback(async () => {
    setLoading(true);
    try {
      const [rels, vers] = await Promise.all([
        api.listRelations(item.id),
        api.listVersions(item.id),
      ]);
      setRelations(rels);
      setVersions(vers);
      const [attRes, linkRes, backRes] = await Promise.allSettled([
        api.listAttachments(item.id),
        api.listLinks(item.id),
        api.listBacklinks(item.id),
      ]);
      if (attRes.status === "fulfilled" && Array.isArray(attRes.value)) setAttachments(attRes.value);
      if (linkRes.status === "fulfilled" && Array.isArray(linkRes.value)) setLinks(linkRes.value);
      if (backRes.status === "fulfilled" && Array.isArray(backRes.value)) setBacklinks(backRes.value);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [item.id, onError]);

  async function handleUploadAttachment(file: File) {
    setUploading(true);
    try {
      const buf = await file.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      }
      const b64 = btoa(binary);
      const mime = file.type || (file.name.endsWith(".md") ? "text/markdown" : file.name.endsWith(".csv") ? "text/csv" : "text/plain");
      await api.uploadAttachment(item.id, { filename: file.name, mime, content_base64: b64 });
      onNotice(`已上传附件：${file.name}`);
      await loadGovernance();
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteAttachment(attId: string) {
    try {
      await api.deleteAttachment(item.id, attId);
      onNotice("已删除附件引用。");
      await loadGovernance();
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  useEffect(() => {
    setAnalysis(null);
    void loadGovernance();
  }, [loadGovernance]);

  async function handleAnalyze() {
    setAnalyzing(true);
    try {
      setAnalysis(await api.analyzeKnowledge(item.id));
      await loadGovernance();
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleMerge(targetId: string, targetTitle: string) {
    try {
      const result = await api.submitReview({
        item_id: item.id,
        action: "merge_duplicate",
        payload: { target_id: targetId },
        reason: `查重分析判定与「${targetTitle}」重复`,
      });
      if (result.review) {
        onNotice("已提交合并审核，可在「审核」页签批准。");
      }
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function handleRestore(version: number) {
    try {
      const result = await api.restoreVersion(item.id, version);
      if (result.kind === "review") {
        onNotice("已提交回滚审核，可在「审核」页签批准。");
      } else {
        onNotice(`已回滚到版本 v${version}。`);
        await loadGovernance();
        onChanged();
      }
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function handleDeleteRelation(relationId: string) {
    try {
      await api.deleteRelation(relationId);
      await loadGovernance();
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  const sectionClass = "rounded-lg border border-slate-800 bg-slate-950/60 p-3";
  const headingClass = "mb-2 text-xs font-medium text-slate-400";

  return (
    <div className="mt-3 space-y-3 border-t border-slate-800 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void handleAnalyze()}
          disabled={analyzing}
          className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          {analyzing ? "分析中…" : "查重分析"}
        </button>
        <span className="text-xs text-slate-500">
          词面召回 + 模型判定（仅 generate，不依赖向量）
        </span>
      </div>

      {analysis && (
        <div className={sectionClass} role="region" aria-label="查重分析结果">
          <h4 className={headingClass}>查重分析结果</h4>
          {analysis.duplicates.length === 0 ? (
            <p className="text-xs text-slate-500">未发现重复候选。</p>
          ) : (
            <ul className="space-y-1">
              {analysis.duplicates.map((d) => (
                <li
                  key={d.item_id}
                  className="flex items-center justify-between gap-2 text-xs text-amber-300"
                >
                  <span>
                    疑似重复：{d.title}（置信度 {(d.score * 100).toFixed(0)}%）
                  </span>
                  <button
                    type="button"
                    onClick={() => void handleMerge(d.item_id, d.title)}
                    className="shrink-0 rounded-md border border-amber-800 px-2 py-0.5 text-xs text-amber-300 hover:bg-amber-950/40"
                  >
                    合并
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-xs text-slate-500">
            本次推断关系 {analysis.relations.length} 条（已落库，见下方关系分区）。
          </p>
        </div>
      )}

      {loading ? (
        <p role="status" className="text-xs text-slate-500">
          正在加载治理信息…
        </p>
      ) : (
        <>
          <div className={sectionClass}>
            <h4 className={headingClass}>关系（{relations.length}）</h4>
            {relations.length === 0 ? (
              <p className="text-xs text-slate-500">暂无关系。可运行查重分析推断。</p>
            ) : (
              <ul className="space-y-1">
                {relations.map((r) => {
                  const outgoing = r.source_id === item.id;
                  const otherId = outgoing ? r.target_id : r.source_id;
                  return (
                    <li
                      key={r.id}
                      className="flex items-center justify-between gap-2 text-xs text-slate-300"
                    >
                      <span>
                        {outgoing ? "→" : "←"} {RELATION_LABEL[r.relation_type]} ·{" "}
                        {otherId.slice(0, 8)}… · {ORIGIN_LABEL[r.origin]} ·{" "}
                        {(r.confidence * 100).toFixed(0)}%
                      </span>
                      <div className="flex shrink-0 items-center gap-1.5">
                        {onNavigateItem && (
                          <button
                            type="button"
                            onClick={() => onNavigateItem(otherId)}
                            className="rounded-md border px-2 py-0.5 text-xs font-medium hover:opacity-85"
                            style={{
                              borderColor: "var(--nf-accent-border, rgba(59,116,232,0.35))",
                              color: "var(--nf-accent, #3b74e8)",
                            }}
                          >
                            定位 →
                          </button>
                        )}
                        <button
                        type="button"
                        onClick={() => void handleDeleteRelation(r.id)}
                        aria-label={`删除关系 ${r.id}`}
                        className="shrink-0 rounded-md border border-slate-700 px-2 py-0.5 text-xs text-red-400 hover:bg-red-950/40"
                      >
                          删除
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className={sectionClass}>
            <h4 className={headingClass}>版本（{versions.length}）</h4>
            {versions.length === 0 ? (
              <p className="text-xs text-slate-500">
                暂无历史版本。编辑 / 合并 / 回滚会自动建立快照。
              </p>
            ) : (
              <ul className="space-y-1">
                {versions.map((v) => (
                  <li
                    key={v.id}
                    className="flex items-center justify-between gap-2 text-xs text-slate-300"
                  >
                    <span>
                      v{v.version} · {v.change_summary ?? "快照"} · {v.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleRestore(v.version)}
                      className="shrink-0 rounded-md border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      回滚
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={sectionClass}>
            <h4 className={headingClass}>来源（{item.source_refs.length}）</h4>
            {item.source_refs.length === 0 ? (
              <p className="text-xs text-slate-500">暂无来源记录。</p>
            ) : (
              <ul className="space-y-1">
                {item.source_refs.map((s) => (
                  <li key={s.id} className="text-xs text-slate-400">
                    {SOURCE_LABEL[s.source_type] ?? s.source_type}
                    {s.conversation_id && ` · 会话 ${s.conversation_id.slice(0, 8)}…`}
                    {s.uri && ` · ${s.uri}`}
                    {s.excerpt && (
                      <span className="block truncate text-slate-600">{s.excerpt}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={sectionClass}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 className="text-xs font-medium text-slate-400">附件（{attachments.length}）</h4>
              <div className="flex items-center gap-2">
                <a
                  href={api.exportSingleMarkdownUrl(item.id)}
                  download
                  className="rounded-md border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
                >
                  导出 .md
                </a>
                {item.status !== "archived" && (
                  <label className="cursor-pointer rounded-md border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800">
                    {uploading ? "上传中…" : "上传附件"}
                    <input
                      type="file"
                      className="hidden"
                      disabled={uploading}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void handleUploadAttachment(f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </div>
            </div>
            {attachments.length === 0 ? (
              <p className="text-xs text-slate-500">
                暂无附件（支持 PNG/JPG/GIF/WEBP/PDF/TXT/MD/CSV，≤10 MiB，禁止 SVG）。
              </p>
            ) : (
              <ul className="space-y-1">
                {attachments.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 text-xs text-slate-300">
                    <a
                      href={api.downloadAttachmentUrl(item.id, a.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate underline hover:opacity-80"
                    >
                      {a.filename}（{(a.size / 1024).toFixed(1)} KB · {a.mime}）
                    </a>
                    <button
                      type="button"
                      onClick={() => void handleDeleteAttachment(a.id)}
                      className="shrink-0 rounded-md border border-slate-700 px-2 py-0.5 text-xs text-red-400 hover:bg-red-950/40"
                    >
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={sectionClass}>
            <h4 className={headingClass}>
              双链（出链 {links.length} · 反链 {backlinks.length}）
            </h4>
            {links.length === 0 && backlinks.length === 0 ? (
              <p className="text-xs text-slate-500">暂无 [[wikilink]] 出链或反链。</p>
            ) : (
              <div className="space-y-1 text-xs text-slate-300">
                {links.map((l) => (
                  <div key={l.id}>→ [[{l.target_title}]]（{l.resolution}）</div>
                ))}
                {backlinks.map((b) => (
                  <div key={b.id}>← 引用自条目 {b.source_id.slice(0, 8)}…</div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}