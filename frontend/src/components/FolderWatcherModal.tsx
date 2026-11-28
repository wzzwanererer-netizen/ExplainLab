import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FolderPreset, FolderScanReport, WatchedFolder } from "../api/types";

interface Props {
  open: boolean;
  onClose: () => void;
  onChanged: (openSpaceId?: string) => void;
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 乱文件夹哨兵（Folder Watcher）管理弹窗：
 * 严格只读监听本地杂乱文件夹（桌面/下载/资料库），支持一键扫描收编多格式文档、图片与音视频，
 * 以及一键在资源管理器中定位原文件所在目录。
 */
export function FolderWatcherModal({ open, onClose, onChanged }: Props) {
  const [folders, setFolders] = useState<WatchedFolder[]>([]);
  const [presets, setPresets] = useState<FolderPreset[]>([]);
  const [loading, setLoading] = useState(false);
  const [pathInput, setPathInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [useAi, setUseAi] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastReport, setLastReport] = useState<FolderScanReport | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [fList, pList] = await Promise.all([
        api.listWatchedFolders(),
        api.listFolderPresets(),
      ]);
      setFolders(fList);
      setPresets(pList);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setNotice(null);
      setLastReport(null);
      void load();
    }
  }, [open, load]);

  if (!open) return null;

  async function handleAdd() {
    const p = pathInput.trim();
    if (!p) return;
    setBusyId("__add__");
    setError(null);
    setNotice(null);
    try {
      const created = await api.addWatchedFolder({
        path: p,
        name: nameInput.trim() || null,
        use_ai_summary: useAi,
      });
      setPathInput("");
      setNameInput("");
      await load();
      onChanged(created.space_id);
      setNotice(
        `已登记监控目录「${created.name}」（发现 ${created.file_count} 个支持的文件），点击「立即扫描收编」即可自动入库。`,
      );
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleScan(f: WatchedFolder, batchSize?: number) {
    setBusyId(f.id);
    setError(null);
    setNotice(null);
    setLastReport(null);
    try {
      const limit = batchSize ?? (f.use_ai_summary ? 20 : 200);
      const report = await api.scanWatchedFolder(f.id, limit);
      setLastReport(report);
      await load();
      onChanged();
      if (report.created_items.length > 0) {
        setNotice(
          `收编完成！从「${f.name}」扫描了 ${report.scanned_files} 个新文件，自动入库 ${report.created_items.length} 条知识。`,
        );
      } else if (report.scanned_files === 0) {
        setNotice(`「${f.name}」里的文件都已经收编过了，目前没有新增或修改的文件。`);
      } else {
        setNotice(`已检查 ${report.scanned_files} 个文件（同名已跳过 ${report.skipped_files} 个）。`);
      }
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleToggleAi(f: WatchedFolder) {
    try {
      await api.patchWatchedFolder(f.id, { use_ai_summary: !f.use_ai_summary });
      await load();
    } catch (err) {
      setError(errMsg(err));
    }
  }

  async function handleRemove(f: WatchedFolder) {
    if (!window.confirm(`移除对「${f.name}」的监听？（绝不会删除你电脑上的任何原文件）`)) {
      return;
    }
    try {
      await api.deleteWatchedFolder(f.id);
      await load();
      setNotice(`已取消对「${f.name}」的监听。`);
    } catch (err) {
      setError(errMsg(err));
    }
  }

  async function handleReveal(path: string) {
    try {
      await api.revealLocalPath(path);
    } catch (err) {
      setError(errMsg(err));
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="乱文件夹哨兵"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
        style={{
          background: "var(--nesti-surface-1, #ffffff)",
          borderColor: "var(--nesti-border-strong, #cbd5e1)",
          color: "var(--nesti-text-primary, #0f172a)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between gap-2 border-b px-5 py-3.5"
          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
        >
          <div>
            <h2 className="text-base font-semibold">乱文件夹哨兵 · 严格只读收编</h2>
            <p className="mt-0.5 text-xs" style={{ color: "var(--nesti-text-tertiary, #64748b)" }}>
              指定桌面/下载/资料文件夹，自动解析 Markdown、Word、PDF、代码、图片与音视频入库，绝不改动原文件。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-2.5 py-1.5 text-xs"
            style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
          >
            关闭
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500">
              {error}
            </div>
          )}
          {notice && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-400">
              {notice}
            </div>
          )}

          {/* 添加新监控文件夹 */}
          <div
            className="space-y-2.5 rounded-xl border p-3.5"
            style={{
              background: "var(--nesti-surface-0, #f8fafc)",
              borderColor: "var(--nesti-border-subtle, #e2e8f0)",
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold">添加要监控的本地文件夹</span>
              {presets.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] opacity-65">快捷填入：</span>
                  {presets.map((p) => (
                    <button
                      key={p.path}
                      type="button"
                      onClick={() => {
                        setPathInput(p.path);
                        setNameInput(p.label.split(" ")[0]);
                      }}
                      className="rounded-full border px-2 py-0.5 text-[11px]"
                      style={{
                        background: "var(--nesti-surface-1, #ffffff)",
                        borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <input
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                placeholder="输入文件夹完整路径，如：D:\资料库 或 C:\Users\wzz\Desktop"
                className="min-w-[240px] flex-1 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              />
              <input
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder="可选别名"
                className="w-28 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              />
              <button
                type="button"
                onClick={() => void handleAdd()}
                disabled={!pathInput.trim() || busyId === "__add__"}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-45"
                style={{ background: "var(--nesti-accent, #2463eb)" }}
              >
                {busyId === "__add__" ? "添加中…" : "+ 加入监控"}
              </button>
            </div>

            <label className="inline-flex items-center gap-1.5 text-[11px] opacity-80">
              <input
                type="checkbox"
                checked={useAi}
                onChange={(e) => setUseAi(e.target.checked)}
              />
              <span>
                开启 AI 智能总结（不勾选则走 L1 极速收编：零费用、1 秒入库，随时可改）
              </span>
            </label>
          </div>

          {lastReport && lastReport.created_items.length > 0 && (
            <div
              className="rounded-xl border p-3 text-xs"
              style={{
                background: "var(--nesti-surface-0, #f8fafc)",
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
              }}
            >
              <div className="mb-1.5 font-semibold">本次新收编入库文件：</div>
              <ul className="space-y-1">
                {lastReport.created_items.map((it) => (
                  <li key={it.id} className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
                        {it.kind}
                      </span>{" "}
                      {it.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleReveal(it.file_path)}
                      className="shrink-0 text-[11px] underline opacity-75 hover:opacity-100"
                    >
                      定位原文件
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 已监控目录列表 */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider opacity-70">
              已登记的监控文件夹（{folders.length}）
            </h3>
            {loading ? (
              <p className="py-4 text-center text-xs opacity-65">加载监控列表…</p>
            ) : folders.length === 0 ? (
              <div
                className="rounded-xl border border-dashed py-6 text-center text-xs opacity-70"
                style={{ borderColor: "var(--nesti-border-strong, #cbd5e1)" }}
              >
                还没有添加监控文件夹。点上方「桌面 / 下载 / 文档」快捷按钮即可一键加入！
              </div>
            ) : (
              folders.map((f) => (
                <div
                  key={f.id}
                  className="flex flex-col justify-between gap-2.5 rounded-xl border p-3 sm:flex-row sm:items-center"
                  style={{
                    background: "var(--nesti-surface-0, #f8fafc)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">{f.name}</span>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                        style={{
                          background: "color-mix(in srgb, var(--nesti-accent, #2463eb) 14%, transparent)",
                          color: "var(--nesti-accent, #2463eb)",
                        }}
                      >
                        已收编 {f.indexed_count} / {f.file_count} 文件
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleToggleAi(f)}
                        className="rounded-full border px-2 py-0.5 text-[10px]"
                        style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                      >
                        {f.use_ai_summary ? "L2 AI 总结：开" : "L1 免费极速：开"}
                      </button>
                    </div>
                    <p className="truncate font-mono text-[11px] opacity-65" title={f.path}>
                      {f.path}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => void handleScan(f)}
                      disabled={busyId === f.id}
                      className="rounded-lg px-2.5 py-1 text-xs font-medium text-white disabled:opacity-45"
                      style={{ background: "var(--nesti-accent, #2463eb)" }}
                    >
                      {busyId === f.id ? "扫描中…" : "扫描收编"}
                    </button>
                    {!f.use_ai_summary && f.indexed_count < f.file_count && (
                      <button
                        type="button"
                        onClick={() => void handleScan(f, 2000)}
                        disabled={busyId === f.id}
                        className="rounded-lg border px-2.5 py-1 text-xs font-medium disabled:opacity-45"
                        style={{
                          borderColor: "var(--nesti-accent, #2463eb)",
                          color: "var(--nesti-accent, #2463eb)",
                        }}
                      >
                        一键全收 ({f.file_count - f.indexed_count})
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        onChanged(f.space_id);
                        onClose();
                      }}
                      className="rounded-lg border px-2.5 py-1 text-xs"
                      style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                    >
                      查看知识
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleReveal(f.path)}
                      className="rounded-lg border px-2.5 py-1 text-xs"
                      style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                    >
                      打开目录
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleRemove(f)}
                      className="rounded-lg border px-2 py-1 text-xs text-red-500"
                      style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                    >
                      移除
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
