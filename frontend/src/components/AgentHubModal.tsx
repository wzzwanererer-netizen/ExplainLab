import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AgentStatus, SessionFilePreview, VacuumReport } from "../api/types";

interface Props {
  open: boolean;
  initialMode?: "manage" | "picker";
  initialAgentName?: string | null;
  onClose: () => void;
  onChanged: (openSpaceId?: string) => void;
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 小白友好版「AI 助手副库 & 自动吸尘器」管理弹窗：
 * 1. 自动扫描本机已安装的 AI 助手，一键为每个助手单开专属副库；
 * 2. 一键吸尘本地对话记录（自动脱敏、提炼高价值知识写入对应副库）；
 * 3. 支持手动添加任意自定义 AI 助手（如 Nesti 3D 桌宠）。
 */
export function AgentHubModal({
  open,
  initialMode = "manage",
  initialAgentName = null,
  onClose,
  onChanged,
}: Props) {
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [vacuuming, setVacuuming] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customDir, setCustomDir] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<VacuumReport | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 自定义吸尘：查看某 Agent 全部对话并自由勾选
  const [pickerAgent, setPickerAgent] = useState<AgentStatus | null>(null);
  const [pickerSessions, setPickerSessions] = useState<SessionFilePreview[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAgents(await api.discoverAgents());
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setReport(null);
    setNotice(null);
    setPickerAgent(null);
    setPickerSessions([]);
    setSelectedFiles(new Set());
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await api.discoverAgents();
        setAgents(list);
        if (initialMode === "picker") {
          const target =
            (initialAgentName
              ? list.find(
                  (a) =>
                    a.name.toLowerCase() === initialAgentName.toLowerCase() ||
                    a.id.toLowerCase() === initialAgentName.toLowerCase(),
                )
              : undefined) ??
            list.find((a) => a.connected && a.session_files_count > 0) ??
            list.find((a) => a.session_files_count > 0);
          if (target) {
            setPickerAgent(target);
            setPickerLoading(true);
            try {
              setPickerSessions(await api.listAgentSessions(target.id));
            } finally {
              setPickerLoading(false);
            }
          }
        }
      } catch (err) {
        setError(errMsg(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [open, initialMode, initialAgentName]);

  if (!open) return null;

  async function handleConnect(agent: AgentStatus) {
    setBusyId(agent.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.addAgent({
        name: agent.name,
        description: agent.description,
        write_rule: true,
      });
      await load();
      onChanged(updated.space_id ?? undefined);
      setNotice(
        `已为「${updated.name}」开通专属副库（${updated.space_name}）${
          updated.rule_installed ? "，并自动写入了记忆同步规则" : ""
        }。`,
      );
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleAddCustom() {
    const name = customName.trim();
    if (!name) return;
    setBusyId("__custom__");
    setError(null);
    setNotice(null);
    try {
      const updated = await api.addAgent({
        name,
        session_dir: customDir.trim() || null,
        write_rule: true,
      });
      setCustomName("");
      setCustomDir("");
      await load();
      onChanged(updated.space_id ?? undefined);
      setNotice(`已添加「${updated.name}」并单开专属副库！`);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleOpenPicker(agent: AgentStatus) {
    setPickerAgent(agent);
    setPickerLoading(true);
    setSelectedFiles(new Set());
    setError(null);
    try {
      const rows = await api.listAgentSessions(agent.id);
      setPickerSessions(rows);
    } catch (err) {
      setError(errMsg(err));
      setPickerSessions([]);
    } finally {
      setPickerLoading(false);
    }
  }

  function toggleFile(filePath: string) {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(filePath)) next.delete(filePath);
      else next.add(filePath);
      return next;
    });
  }

  async function handleVacuumSelected() {
    if (!pickerAgent || selectedFiles.size === 0) return;
    setVacuuming(true);
    setError(null);
    setNotice(null);
    setReport(null);
    try {
      const res = await api.vacuumAgents(
        pickerAgent.name,
        selectedFiles.size,
        [...selectedFiles],
      );
      setReport(res);
      await load();
      const refreshed = await api.listAgentSessions(pickerAgent.id);
      setPickerSessions(refreshed);
      setSelectedFiles(new Set());
      onChanged();
      if (res.created_items.length > 0) {
        setNotice(
          `自定义吸尘完成！从你勾选的 ${res.scanned_sessions} 份对话中提炼并存入了 ${res.created_items.length} 条知识。`,
        );
      } else {
        setNotice(
          `已扫描你勾选的 ${res.scanned_sessions} 份对话，未发现新增高价值条目（或已存在同名知识）。`,
        );
      }
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setVacuuming(false);
    }
  }

  async function handleVacuum(agentName?: string) {
    setVacuuming(true);
    setError(null);
    setNotice(null);
    setReport(null);
    try {
      const res = await api.vacuumAgents(agentName ?? null, 3);
      setReport(res);
      await load();
      onChanged();
      if (res.created_items.length > 0) {
        setNotice(
          `吸尘完成！扫描了 ${res.scanned_sessions} 份新对话，自动提炼并存进了 ${res.created_items.length} 条高价值知识。`,
        );
      } else if (res.scanned_sessions === 0) {
        setNotice("所有已接入助手的本地对话都是最新状态，暂时没有未处理的新对话。");
      } else {
        setNotice(
          `已扫描 ${res.scanned_sessions} 份对话，均为闲聊或过程日志，已自动过滤（宁缺毋滥）。`,
        );
      }
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setVacuuming(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="AI 助手副库管理与自动吸尘器"
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
        {/* 顶部标题 */}
        <div
          className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3.5"
          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
        >
          <div>
            <h2 className="text-base font-semibold">AI 助手副库管理 · 本地对话吸尘器</h2>
            <p className="mt-0.5 text-xs" style={{ color: "var(--nesti-text-tertiary, #64748b)" }}>
              你电脑里每装一个 AI 助手，点一下就能为它单开一个专属副库，并自动把聊天干货「吸」进知识库。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleVacuum()}
              disabled={vacuuming || loading}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-45"
              style={{ background: "var(--nesti-accent, #2463eb)" }}
            >
              {vacuuming ? "正在吸尘提炼新对话…" : "一键吸尘全部新对话"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border px-2.5 py-1.5 text-xs hover:opacity-80"
              style={{
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                color: "var(--nesti-text-secondary, #475569)",
              }}
            >
              关闭
            </button>
          </div>
        </div>

        {/* 主体内容 */}
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
          {report && report.created_items.length > 0 && (
            <div
              className="rounded-xl border p-3 text-xs"
              style={{
                background: "var(--nesti-surface-0, #f8fafc)",
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
              }}
            >
              <div className="mb-1.5 font-semibold">本次自动吸尘新入库知识：</div>
              <ul className="space-y-1">
                {report.created_items.map((it) => (
                  <li key={it.id} className="flex items-center justify-between gap-2">
                    <span>
                      <span className="font-medium text-blue-600 dark:text-blue-400">
                        [{it.agent_name}]
                      </span>{" "}
                      {it.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        onChanged(it.space_id);
                        onClose();
                      }}
                      className="shrink-0 text-[11px] underline opacity-80 hover:opacity-100"
                    >
                      去查看
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 自定义吸尘置顶面板：点开「自选对话吸尘」立刻在最上方呈现，支持一键切换不同助手 */}
          {pickerAgent && (
            <div
              className="space-y-2.5 rounded-xl border-2 p-3.5 shadow-sm"
              style={{
                background: "var(--nesti-surface-0, #f8fafc)",
                borderColor: "var(--nesti-accent, #2463eb)",
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold">
                    自定义吸尘 · {pickerAgent.name} 本地全部对话（共 {pickerSessions.length} 条）
                  </div>
                  <div className="text-[11px] opacity-70">
                    勾选你想存进知识库的对话，点击右侧按钮精准提炼入库（不影响自动吸尘）。
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedFiles(
                        new Set(
                          pickerSessions
                            .filter((s) => !s.processed)
                            .slice(0, 10)
                            .map((s) => s.file_path),
                        ),
                      )
                    }
                    className="rounded-md border px-2 py-1 text-[11px]"
                    style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                  >
                    勾选未吸尘
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedFiles(new Set())}
                    className="rounded-md border px-2 py-1 text-[11px]"
                    style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                  >
                    清空勾选
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleVacuumSelected()}
                    disabled={vacuuming || selectedFiles.size === 0}
                    className="rounded-md px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-45"
                    style={{ background: "var(--nesti-accent, #2463eb)" }}
                  >
                    {vacuuming
                      ? "正在提炼选中对话…"
                      : `提炼并存入选中 (${selectedFiles.size})`}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPickerAgent(null)}
                    className="rounded-md border px-2 py-1 text-[11px]"
                    style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                  >
                    收起
                  </button>
                </div>
              </div>

              {/* 快捷切换其他有本地对话的 AI 助手 */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] opacity-65">切换助手：</span>
                {agents
                  .filter((a) => a.connected && a.session_files_count > 0)
                  .map((a) => {
                    const active = a.id === pickerAgent.id;
                    return (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => void handleOpenPicker(a)}
                        className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                        style={
                          active
                            ? {
                                background: "var(--nesti-accent, #2463eb)",
                                borderColor: "var(--nesti-accent, #2463eb)",
                                color: "#ffffff",
                              }
                            : {
                                background: "var(--nesti-surface-1, #ffffff)",
                                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                              }
                        }
                      >
                        {a.name} ({a.session_files_count})
                      </button>
                    );
                  })}
              </div>

              {pickerLoading ? (
                <p className="py-4 text-center text-xs opacity-70">
                  正在读取 {pickerAgent.name} 的全部本地聊天清单…
                </p>
              ) : pickerSessions.length === 0 ? (
                <p className="py-4 text-center text-xs opacity-70">
                  未在该助手目录下找到可读的本地聊天记录。
                </p>
              ) : (
                <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
                  {pickerSessions.map((s) => {
                    const checked = selectedFiles.has(s.file_path);
                    return (
                      <label
                        key={s.file_path}
                        className="flex cursor-pointer items-start gap-2.5 rounded-lg border p-2 text-xs transition-colors"
                        style={{
                          background: checked
                            ? "color-mix(in srgb, var(--nesti-accent, #2463eb) 8%, var(--nesti-surface-1, #ffffff))"
                            : "var(--nesti-surface-1, #ffffff)",
                          borderColor: checked
                            ? "var(--nesti-accent, #2463eb)"
                            : "var(--nesti-border-subtle, #e2e8f0)",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleFile(s.file_path)}
                          className="mt-0.5 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-medium">{s.label}</span>
                            <span
                              className="rounded-full px-1.5 py-0.5 text-[10px]"
                              style={
                                s.processed && s.created_count > 0
                                  ? { background: "rgba(16,185,129,0.14)", color: "#059669" }
                                  : s.processed
                                    ? { background: "rgba(148,163,184,0.18)", color: "#64748b" }
                                    : { background: "rgba(245,158,11,0.14)", color: "#d97706" }
                              }
                            >
                              {s.processed && s.created_count > 0
                                ? `已入库 ${s.created_count} 条`
                                : s.processed
                                  ? "已扫描(0条入库)"
                                  : "未吸尘"}
                            </span>
                            <span className="ml-auto font-mono text-[10px] opacity-60">
                              {new Date(s.updated_at).toLocaleString("zh-CN", {
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}{" "}
                              · {s.size_kb} KB
                            </span>
                          </div>
                          <p className="mt-0.5 truncate text-[11px] opacity-75" title={s.preview}>
                            {s.preview}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 自动发现的本机 Agent 列表 */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider opacity-70">
                本机自动检测到的 AI 助手（{agents.filter((a) => a.installed).length} 个已安装）
              </h3>
              <button
                type="button"
                onClick={() => void load()}
                disabled={loading}
                className="text-xs opacity-70 hover:opacity-100"
              >
                {loading ? "扫描中…" : "重新扫描"}
              </button>
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2">
              {agents.map((ag) => (
                <div
                  key={ag.id}
                  className="flex flex-col justify-between gap-2.5 rounded-xl border p-3"
                  style={{
                    background: "var(--nesti-surface-0, #f8fafc)",
                    borderColor: ag.connected
                      ? "color-mix(in srgb, var(--nesti-accent, #2463eb) 40%, transparent)"
                      : "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{ag.name}</span>
                      <div className="flex items-center gap-1">
                        {ag.installed && (
                          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                            本机已装
                          </span>
                        )}
                        <span
                          className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                          style={
                            ag.connected
                              ? {
                                  background: "color-mix(in srgb, var(--nesti-accent, #2463eb) 15%, transparent)",
                                  color: "var(--nesti-accent, #2463eb)",
                                }
                              : {
                                  background: "rgba(148,163,184,0.18)",
                                  color: "var(--nesti-text-tertiary, #64748b)",
                                }
                          }
                        >
                          {ag.connected ? `副库 ${ag.item_count} 条` : "未开通副库"}
                        </span>
                      </div>
                    </div>
                    <p className="text-[11px] opacity-70">{ag.description}</p>
                    <p className="text-[11px] opacity-75">
                      {ag.session_files_count > 0
                        ? `检测到 ${ag.session_files_count} 份本地对话（${ag.unprocessed_count} 份待吸尘）`
                        : "暂未检测到本地对话文件（仍可先开通副库）"}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    {!ag.connected ? (
                      <button
                        type="button"
                        onClick={() => void handleConnect(ag)}
                        disabled={busyId === ag.id}
                        className="rounded-lg px-2.5 py-1 text-xs font-medium text-white disabled:opacity-45"
                        style={{ background: "var(--nesti-accent, #2463eb)" }}
                      >
                        {busyId === ag.id ? "开通中…" : "一键开通专属副库"}
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            if (ag.space_id) onChanged(ag.space_id);
                            onClose();
                          }}
                          className="rounded-lg border px-2.5 py-1 text-xs hover:opacity-80"
                          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                        >
                          进入副库
                        </button>
                        {ag.session_files_count > 0 && (
                          <>
                            <button
                              type="button"
                              onClick={() => void handleVacuum(ag.name)}
                              disabled={vacuuming}
                              className="rounded-lg px-2.5 py-1 text-xs font-medium text-white disabled:opacity-45"
                              style={{ background: "var(--nesti-accent, #2463eb)" }}
                            >
                              {vacuuming
                                ? "吸尘中…"
                                : ag.unprocessed_count > 0
                                  ? `自动吸尘 (${ag.unprocessed_count})`
                                  : "自动再扫"}
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleOpenPicker(ag)}
                              disabled={vacuuming}
                              className="rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors hover:opacity-85 disabled:opacity-45"
                              style={{
                                borderColor: "var(--nesti-border-strong, #cbd5e1)",
                                color: "var(--nesti-text-primary, #0f172a)",
                              }}
                            >
                              自选对话吸尘
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 手动添加自定义 Agent */}
          <div
            className="space-y-2.5 rounded-xl border p-3.5"
            style={{
              background: "var(--nesti-surface-0, #f8fafc)",
              borderColor: "var(--nesti-border-subtle, #e2e8f0)",
            }}
          >
            <div className="text-xs font-semibold">
              没有找到你的工具？手动添加新 AI 助手 / 桌宠（如 Nesti 3D、ZCode）
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="助手名称，例如：Nesti 3D 桌宠"
                className="min-w-[180px] flex-1 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              />
              <input
                value={customDir}
                onChange={(e) => setCustomDir(e.target.value)}
                placeholder="可选：本地聊天记录目录路径"
                className="min-w-[200px] flex-1 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              />
              <button
                type="button"
                onClick={() => void handleAddCustom()}
                disabled={!customName.trim() || busyId === "__custom__"}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-45"
                style={{ background: "var(--nesti-accent, #2463eb)" }}
              >
                {busyId === "__custom__" ? "添加中…" : "+ 添加并开通副库"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
