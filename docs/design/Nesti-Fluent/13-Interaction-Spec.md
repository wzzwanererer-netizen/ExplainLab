# 13 · Interaction Specification（桌面交互规范与完整流程示例）

## 1. 十种标准交互状态矩阵
| 状态 | 视觉与行为规范 |
| --- | --- |
| Normal | `--nf-bg-surface` + `1px --nf-border-default`，静默克制 |
| Hover | 120ms 过渡至 `--nf-bg-surface-hover` 与 `--nf-border-strong` |
| Active | 轻微按压反馈或 `--nf-bg-surface-active` |
| Selected | `--nf-accent-soft` 底色 + `--nf-accent-border` 描边 + 左侧 `3px` 指示条（主导航） |
| Disabled | `opacity: 0.45` + `cursor: not-allowed`，屏蔽点击与键盘激活 |
| Loading | 局部骨架/状态条，不锁死顶栏与页签切换 |
| Empty | 1px 虚线框 + 清晰下一步操作指引（无虚假示例数据） |
| Error | `--nf-status-danger-bg` + 中文错误映射（如 `ATTACHMENT_ITEM_ARCHIVED` → 「已归档条目禁止上传附件」） |
| Confirmation | 破坏性操作（删会话、删最后一条附件引用、驳回导入）必须二次确认 |
| Success | 底部右侧克制 Toast（2.6s 自动消失）或行内状态更新 |

## 2. 完整端到端交互流程示例：Active ZIP 含附件导入 → 审核批准 → 正式附件查看

1. **拖放或选择 ZIP（Knowledge 页）**：用户点击「导入 MD / ZIP」或拖放 `.zip` 文件至知识库工作区 → 前端校验扩展名与单包体积（≤100 MiB）→ 读取为 Base64 调用 `POST /api/knowledge/import`。
2. **后端返回 `202 Accepted`（Pending Review）**：界面不刷新虚假附件，弹出状态提示「已生成 Active 导入审核单，附件暂存至隔离 staging」，顶栏通知铃铛红点与左侧「审核队列」角标即时 `+1`。
3. **进入审核队列（Reviews 页）**：用户点击通知或 `Ctrl+K` 跳转审核队列，左侧选中 `Active ZIP 导入` 条目 → 中央展示正文红绿 Diff 与 `__a1_import` 附件清单（文件名、MIME、大小、SHA-256）。
4. **填写备注并批准**：用户输入可选备注，点击「批准并发布附件」→ 按钮进入 `Loading` → 调用 `POST /api/reviews/{id}/approve`。
5. **收敛反馈**：返回 `200 OK` 后，Toast 提示「审批已提交，正式附件已发布」，审核单移入「已批准」；若后端日志出现独立索引同步降级，业务响应仍保持成功，符合 P1-01 契约。用户在知识库选中该条目，检查器「附件」Tab 立即展示已发布附件并支持流式下载。
